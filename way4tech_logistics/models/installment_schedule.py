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
    paid_date = fields.Date(string='Paid Date', tracking=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('due', 'Due Soon'),
        ('overdue', 'Overdue'),
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
            vehicle_name = rec.vehicle_id.display_name or rec.vehicle_id.license_plate or 'Vehicle'
            rec.name = f'{vehicle_name} — Installment #{rec.installment_number}'

    @api.depends('due_date', 'move_id', 'move_id.state')
    def _compute_state(self):
        today = fields.Date.today()
        due_soon_days = 7
        for rec in self:
            if rec.move_id and rec.move_id.state == 'posted':
                rec.state = 'paid'
            elif rec.due_date and rec.due_date < today:
                rec.state = 'overdue'
            elif rec.due_date and rec.due_date <= today + datetime.timedelta(days=due_soon_days):
                rec.state = 'due'
            else:
                rec.state = 'pending'

    def action_pay(self):
        """Create a draft journal entry for this installment payment."""
        self.ensure_one()
        if self.state == 'paid':
            raise UserError(_('This installment is already paid.'))
        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)
        if not settings.installment_payable_account_id:
            raise UserError(_(
                'Set the Installment Payable Account in\n'
                'Configuration → Payroll & Accounting Setup → Fleet & Trucks tab.'
            ))
        journal = settings.truck_expense_journal_id
        # Credit side: find bank/cash journal for the payment account
        bank_journal = self.env['account.journal'].search(
            [('type', 'in', ['bank', 'cash']), ('company_id', '=', self.company_id.id)],
            limit=1,
        )
        credit_account = bank_journal.default_account_id if bank_journal else False
        if not credit_account:
            raise UserError(_(
                'No bank or cash journal found in your company.\n'
                'Please create a Bank or Cash journal in Accounting → Configuration → Journals.'
            ))
        inst_category = self.env.ref('way4tech_logistics.category_installment', raise_if_not_found=False)
        move_vals = {
            'move_type': 'entry',
            'date': fields.Date.today(),
            'ref': f'Installment #{self.installment_number} — {self.vehicle_id.display_name or self.vehicle_id.license_plate}',
            'company_id': self.company_id.id,
            'line_ids': [
                (0, 0, {
                    'name': f'Installment Payment #{self.installment_number} — {self.vehicle_id.display_name}',
                    'account_id': settings.installment_payable_account_id.id,
                    'debit': self.amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': f'Installment Payment (Bank) #{self.installment_number} — {self.vehicle_id.display_name}',
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': self.amount,
                }),
            ],
        }
        if inst_category:
            move_vals['way4tech_category_id'] = inst_category.id
        if journal:
            move_vals['journal_id'] = journal.id
        move = self.env['account.move'].create(move_vals)
        self.write({'move_id': move.id, 'paid_date': fields.Date.today()})
        self.vehicle_id.installments_paid = (self.vehicle_id.installments_paid or 0) + 1
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': move.id,
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
