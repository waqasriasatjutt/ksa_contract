import datetime
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class Way4TechInstallmentSchedule(models.Model):
    """
    Detailed monthly installment payment schedule for vehicles purchased on financing.
    Linked from fleet.vehicle (installment_schedule_ids).
    Can auto-generate schedule from vehicle installment fields.
    """
    _name = 'way4tech.installment.schedule'
    _description = 'Vehicle Installment Payment Schedule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'vehicle_id, installment_number'

    name = fields.Char(
        string='Reference',
        compute='_compute_name',
        store=True,
    )
    vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Vehicle', required=True,
        tracking=True, ondelete='cascade', index=True,
    )
    installment_number = fields.Integer(string='Installment #', required=True)
    due_date = fields.Date(string='Due Date', required=True, tracking=True)
    amount = fields.Monetary(string='Amount', required=True, tracking=True)
    paid_date = fields.Date(string='Paid Date', compute='_compute_paid_date', store=True, tracking=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('due', 'Due Soon'),
        ('overdue', 'Overdue'),
        ('invoiced', 'Invoiced'),
        ('posted', 'Posted'),
        ('paid', 'Paid'),
    ], string='Status', compute='_compute_state', store=True, tracking=True)
    move_id = fields.Many2one(
        'account.move', string='Payment Entry',
        readonly=True, copy=False,
    )
    note = fields.Char(string='Note')
    company_id = fields.Many2one(
        'res.company', related='vehicle_id.company_id',
        store=True, readonly=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='vehicle_id.currency_id',
        store=True, readonly=True,
    )

    @api.depends('vehicle_id', 'installment_number')
    def _compute_name(self):
        for rec in self:
            # 2026-10-03: the plate first. Odoo's own display_name is built from
            # the model and the brand, so a vehicle without them reads
            # "//No Plate" and that was ending up on the bill.
            rec.name = '%s — Installment #%02d' % (
                rec.vehicle_id._way4tech_label(), rec.installment_number)

    @api.depends('due_date', 'move_id', 'move_id.state', 'move_id.payment_state')
    def _compute_state(self):
        today = fields.Date.today()
        due_soon_days = 7
        for rec in self:
            if rec.move_id and rec.move_id.payment_state in ('paid', 'in_payment'):
                rec.state = 'paid'
            elif rec.move_id and rec.move_id.state == 'posted':
                rec.state = 'posted'
            elif rec.move_id and rec.move_id.state == 'draft':
                rec.state = 'invoiced'
            elif rec.due_date and rec.due_date < today:
                rec.state = 'overdue'
            elif rec.due_date and rec.due_date <= today + datetime.timedelta(days=due_soon_days):
                rec.state = 'due'
            else:
                rec.state = 'pending'

    @api.depends('move_id', 'move_id.payment_state')
    def _compute_paid_date(self):
        for rec in self:
            if rec.move_id and rec.move_id.payment_state in ('paid', 'in_payment'):
                rec.paid_date = rec.paid_date or fields.Date.today()
            else:
                rec.paid_date = False

    def action_pay(self):
        """Create a draft vendor bill for this installment payment.

        The user confirms the bill and uses Odoo's standard 'Register Payment'
        to record the bank/cash outflow — proper reconciliation comes for free.
        """
        self.ensure_one()
        if self.state == 'paid':
            raise UserError(_('This installment is already paid.'))
        if self.move_id:
            raise UserError(_('A bill already exists for this installment. Please check it first.'))

        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)
        if not self.amount:
            raise UserError(_(
                'This installment has no amount. Enter it on the schedule line '
                'first.'))

        vendor = self.vehicle_id.installment_vendor_id
        if not vendor:
            raise UserError(_(
                'No Financing Vendor set on this vehicle.\n'
                'Go to Fleet & Vehicles → open the vehicle → set the Financing Vendor field.'
            ))

        analytic = (
            self.vehicle_id.analytic_account_id
            or settings.default_analytic_account_id
        )

        # 2026-10-03: the line carries an EXPENSE account. It used to carry the
        # Installment Payable account, which is a liability, so Odoo did not
        # treat it as an invoice line at all and the bill opened with nothing in
        # it. The payable is the counterpart, set below, not the line.
        label = '%s - Installment #%02d' % (
            self.vehicle_id._way4tech_label(), self.installment_number)
        bill_line = {
            'name': label,
            'quantity': 1.0,
            'price_unit': self.amount,
        }
        expense = (settings.installment_expense_account_id
                   or settings.truck_expense_account_id)
        if expense:
            bill_line['account_id'] = expense.id
        if analytic:
            bill_line['analytic_distribution'] = {str(analytic.id): 100}

        inst_category = self.env.ref('way4tech_logistics.category_installment', raise_if_not_found=False)
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': vendor.id,
            'invoice_date': self.due_date or fields.Date.today(),
            'ref': label,
            'company_id': self.company_id.id,
            'invoice_line_ids': [(0, 0, bill_line)],
        }
        if inst_category:
            bill_vals['way4tech_category_id'] = inst_category.id
        journal = settings._way4tech_installment_bill_journal()
        if journal:
            bill_vals['journal_id'] = journal.id

        bill = self.env['account.move'].create(bill_vals)
        # 2026-10-08: the Installment Payable Account from Payroll &
        # Accounting Setup, not the vendor's default payable. Falls back to the
        # Truck Trip Costs Payable when the installment one is not set.
        settings._way4tech_set_move_counterpart(
            bill, settings.installment_payable_account_id
            or settings.truck_costs_payable_account_id)
        self.write({'move_id': bill.id})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Installment Bill'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': bill.id,
            'target': 'current',
        }

    def action_view_entry(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_('No payment entry linked yet.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
        }

    @api.model
    def _cron_send_due_reminders(self):
        """Weekly cron: email managers about installments due or overdue."""
        today = fields.Date.today()
        due_cutoff = today + datetime.timedelta(days=7)
        records = self.search([
            ('state', 'in', ['pending', 'due', 'overdue']),
            ('due_date', '<=', due_cutoff),
        ])
        if not records:
            return
        try:
            group = self.env.ref('way4tech_logistics.group_logistics_manager')
            managers = group.users.filtered(lambda u: u.email)
        except Exception:
            return
        if not managers:
            return

        state_labels = dict(self._fields['state'].selection)
        rows = ''.join(
            f'<tr style="background:{"#fff3cd" if r.state == "overdue" else "#fff"};">'
            f'<td style="padding:6px 10px;">{r.vehicle_id.display_name}</td>'
            f'<td style="padding:6px 10px;">#{r.installment_number}</td>'
            f'<td style="padding:6px 10px;">{r.due_date}</td>'
            f'<td style="padding:6px 10px;text-align:right;">{r.currency_id.symbol} {r.amount:,.2f}</td>'
            f'<td style="padding:6px 10px;color:{"#dc3545" if r.state == "overdue" else "#fd7e14"};">'
            f'<strong>{state_labels.get(r.state, r.state)}</strong></td>'
            f'</tr>'
            for r in records
        )
        body = f'''
        <div style="font-family:Arial,sans-serif;max-width:650px;">
        <h2 style="color:#dc3545;">Installment Due / Overdue Reminder</h2>
        <p>Date: <strong>{today}</strong></p>
        <table border="0" style="width:100%;border-collapse:collapse;">
          <tr style="background:#495057;color:white;">
            <th style="padding:8px 10px;text-align:left;">Vehicle</th>
            <th style="padding:8px 10px;">Installment #</th>
            <th style="padding:8px 10px;">Due Date</th>
            <th style="padding:8px 10px;text-align:right;">Amount</th>
            <th style="padding:8px 10px;">Status</th>
          </tr>
          {rows}
        </table>
        <p style="color:#888;font-size:12px;">Way4Tech Logistics ERP — Auto Reminder</p>
        </div>
        '''
        for mgr in managers:
            self.env['mail.mail'].sudo().create({
                'subject': f'[Way4Tech] Installment Reminder — {today}',
                'body_html': body,
                'email_to': mgr.email,
                'email_from': self.env.company.email or 'noreply@way4tech.com',
            }).send()
