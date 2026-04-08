from odoo import api, fields, models, _
from odoo.exceptions import UserError


class Way4TechEquipmentRentalInbound(models.Model):
    _name = 'way4tech.equipment.rental.inbound'
    _description = 'Inbound Equipment Rental (From Vendor)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'rental_start desc, name desc'

    name = fields.Char(
        string='Reference', readonly=True, copy=False,
        default=lambda self: _('New'),
    )

    # ── Equipment ─────────────────────────────────────────────────────────────
    equipment_name = fields.Char(
        string='Equipment Description', required=True,
        help='Name or description of the rented equipment / machinery.',
    )
    equipment_category = fields.Selection(
        selection=[
            ('generator', 'Generator'),
            ('crane', 'Crane / Lifting Equipment'),
            ('forklift', 'Forklift'),
            ('excavator', 'Excavator / Earth Mover'),
            ('compressor', 'Air Compressor'),
            ('vehicle', 'Vehicle / Transport'),
            ('tools', 'Tools & Small Equipment'),
            ('yard', 'Yard / Space'),
            ('other', 'Other Machinery'),
        ],
        string='Category', default='other', tracking=True,
    )

    # ── Vendor ────────────────────────────────────────────────────────────────
    vendor_id = fields.Many2one(
        'res.partner', string='Vendor', required=True, tracking=True,
        domain=[('supplier_rank', '>', 0)],
        help='The vendor / supplier who owns the equipment.',
    )
    contact_person = fields.Char(string='Contact Person')
    contact_phone = fields.Char(string='Contact Phone')

    # ── Rental Period ─────────────────────────────────────────────────────────
    rental_start = fields.Date(
        string='Start Date', required=True,
        default=fields.Date.today, tracking=True,
    )
    rental_end = fields.Date(
        string='End Date', tracking=True,
    )
    rate_type = fields.Selection(
        selection=[
            ('daily', 'Daily'),
            ('weekly', 'Weekly'),
            ('monthly', 'Monthly'),
            ('fixed', 'Fixed / Lump Sum'),
        ],
        string='Rate Type', default='daily', required=True, tracking=True,
    )
    rate_amount = fields.Monetary(
        string='Rate', currency_field='currency_id', tracking=True,
        help='Cost per day/week/month or fixed total.',
    )
    rental_duration = fields.Float(
        string='Duration',
        compute='_compute_duration', store=True, readonly=False,
        help='Auto-calculated from dates based on rate type. Override manually if needed.',
    )
    total_cost = fields.Monetary(
        string='Total Cost',
        compute='_compute_total_cost', store=True,
        currency_field='currency_id',
    )

    # ── Project Link (optional) ───────────────────────────────────────────────
    manpower_contract_id = fields.Many2one(
        'way4tech.manpower.contract',
        string='Linked Project/Contract',
        help='If this rental is for a specific project, link it here for cost tracking.',
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Analytic Account',
    )

    # ── Billing ───────────────────────────────────────────────────────────────
    bill_id = fields.Many2one(
        'account.move', string='Vendor Bill',
        readonly=True, copy=False,
    )
    bill_state = fields.Selection(
        related='bill_id.state', string='Bill Status',
        readonly=True, store=False,
    )
    payment_state = fields.Selection(
        related='bill_id.payment_state', string='Payment Status',
        readonly=True, store=False,
    )

    # ── State ─────────────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('active', 'Active'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status', default='draft', tracking=True, copy=False,
    )

    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company, required=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id',
        readonly=True, store=True,
    )
    notes = fields.Text(string='Terms & Notes')

    # ── Computes ──────────────────────────────────────────────────────────────

    @api.depends('rental_start', 'rental_end', 'rate_type')
    def _compute_duration(self):
        for rec in self:
            if not rec.rental_start or not rec.rental_end or rec.rental_end < rec.rental_start:
                if rec.rate_type == 'fixed':
                    rec.rental_duration = 1.0
                else:
                    rec.rental_duration = 0.0
                continue
            days = (rec.rental_end - rec.rental_start).days + 1
            if rec.rate_type == 'daily':
                rec.rental_duration = days
            elif rec.rate_type == 'weekly':
                rec.rental_duration = round(days / 7.0, 2)
            elif rec.rate_type == 'monthly':
                rec.rental_duration = round(days / 30.0, 2)
            elif rec.rate_type == 'fixed':
                rec.rental_duration = 1.0

    @api.depends('rental_duration', 'rate_amount')
    def _compute_total_cost(self):
        for rec in self:
            rec.total_cost = rec.rental_duration * rec.rate_amount

    # ── Sequence ──────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'way4tech.equipment.rental.inbound'
                ) or _('New')
        return super().create(vals_list)

    # ── State Actions ─────────────────────────────────────────────────────────

    def action_confirm(self):
        self.ensure_one()
        if not self.rate_amount:
            raise UserError(_('Please set the rental rate before confirming.'))
        self.state = 'confirmed'

    def action_start(self):
        self.ensure_one()
        self.state = 'active'

    def action_complete(self):
        self.ensure_one()
        self.state = 'completed'

    def action_cancel(self):
        self.ensure_one()
        self.state = 'cancelled'

    def action_reset_draft(self):
        self.ensure_one()
        self.state = 'draft'

    # ── Vendor Bill ───────────────────────────────────────────────────────────

    def action_create_bill(self):
        """Create a vendor bill for the rental cost."""
        self.ensure_one()
        if self.bill_id:
            raise UserError(_('A vendor bill already exists for this rental.'))
        if self.total_cost <= 0:
            raise UserError(_('Total cost is zero. Set rate and duration first.'))

        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)
        expense_account = (
            settings.rental_expense_account_id
            or settings.truck_expense_account_id
        )
        if not expense_account:
            raise UserError(_(
                'Set the Equipment Rental Expense Account in\n'
                'Configuration → Payroll & Accounting Setup.'
            ))

        analytic = self.analytic_account_id or settings.default_analytic_account_id

        # Build description
        rate_labels = {'daily': 'day', 'weekly': 'week', 'monthly': 'month', 'fixed': 'fixed'}
        desc = '%s — %s (%s × %s/%s)' % (
            self.name,
            self.equipment_name,
            self.rental_duration,
            self.currency_id.symbol or '',
            rate_labels.get(self.rate_type, ''),
        )
        if self.rental_start and self.rental_end:
            desc += ' [%s → %s]' % (self.rental_start, self.rental_end)

        bill_line = {
            'name': desc,
            'quantity': self.rental_duration,
            'price_unit': self.rate_amount,
            'account_id': expense_account.id,
        }
        if analytic:
            bill_line['analytic_distribution'] = {str(analytic.id): 100}

        _category = self.env.ref('way4tech_logistics.category_rent', raise_if_not_found=False)
        journal = settings.rental_expense_journal_id
        if not journal or journal.type != 'purchase':
            journal = self.env['account.journal'].search(
                [('type', '=', 'purchase'), ('company_id', '=', self.company_id.id)],
                limit=1,
            )

        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.vendor_id.id,
            'invoice_date': self.rental_end or fields.Date.today(),
            'ref': '%s — %s' % (self.name, self.equipment_name),
            'company_id': self.company_id.id,
            'invoice_line_ids': [(0, 0, bill_line)],
        }
        if _category:
            bill_vals['way4tech_category_id'] = _category.id
        if journal:
            bill_vals['journal_id'] = journal.id

        bill = self.env['account.move'].create(bill_vals)
        self.bill_id = bill.id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_bill(self):
        self.ensure_one()
        if not self.bill_id:
            raise UserError(_('No vendor bill linked to this rental.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'res_id': self.bill_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
