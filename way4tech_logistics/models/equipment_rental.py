from odoo import api, fields, models, _
from odoo.exceptions import UserError


class Way4TechEquipmentRental(models.Model):
    _name = 'way4tech.equipment.rental'
    _description = 'Equipment / Machinery Rental'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'rental_start desc, name desc'

    name = fields.Char(
        string='Reference', readonly=True, copy=False,
        default=lambda self: _('New'),
    )

    # ── Equipment ─────────────────────────────────────────────────────────────
    asset_register_id = fields.Many2one(
        'way4tech.asset.register', string='Asset / Equipment',
        tracking=True,
        help='Link to the fixed asset being rented out. Optional — '
             'if set, the equipment name and category are auto-filled and '
             'the rental income is visible on the asset record.',
    )
    equipment_name = fields.Char(
        string='Equipment Description', required=True,
        help='Name or description of the equipment / machinery being rented.',
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

    # ── Client ────────────────────────────────────────────────────────────────
    client_id = fields.Many2one(
        'res.partner', string='Client', required=True, tracking=True,
    )
    salesperson_id = fields.Many2one('res.users', string='Salesperson', tracking=True)

    # ── Rental Period ─────────────────────────────────────────────────────────
    rental_start = fields.Date(
        string='Rental Start', required=True,
        default=fields.Date.today, tracking=True,
    )
    rental_end = fields.Date(string='Rental End', tracking=True)

    # ── Rate & Revenue ────────────────────────────────────────────────────────
    rate_type = fields.Selection(
        selection=[
            ('daily', 'Daily Rate'),
            ('weekly', 'Weekly Rate'),
            ('monthly', 'Monthly Rate'),
            ('fixed', 'Fixed / Lump Sum'),
        ],
        string='Rate Type', default='daily', required=True,
        help='Daily/Weekly/Monthly: duration is computed from the dates, '
             'revenue = duration × rate.\n'
             'Fixed: enter the total rental price directly in the Revenue field.',
    )
    rate_amount = fields.Monetary(
        string='Rate / Period',
        currency_field='currency_id',
        help='Rate per day / week / month.\n'
             'For Fixed type: this is the total agreed rental price.',
    )
    rental_duration = fields.Float(
        string='Duration',
        compute='_compute_duration', store=True,
        digits=(10, 2),
        help='Auto-calculated from start / end dates based on Rate Type. '
             'Days, weeks, or months.',
    )
    revenue = fields.Monetary(
        string='Rental Revenue',
        compute='_compute_revenue', store=True, readonly=False,
        currency_field='currency_id',
        tracking=True,
        help='Auto-calculated: Duration × Rate. '
             'For Fixed type equals the Rate / Total Price field. '
             'Can be adjusted manually.',
    )

    # ── Accounting ────────────────────────────────────────────────────────────
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Analytic Account',
    )
    invoice_id = fields.Many2one(
        'account.move', string='Customer Invoice', readonly=True, copy=False,
    )
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company, required=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id',
        string='Currency', readonly=True, store=True,
    )

    # ── State ─────────────────────────────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('active', 'Active / Ongoing'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status', default='draft', tracking=True, copy=False,
    )
    notes = fields.Text(string='Notes / Terms')

    # ── Compute Methods ───────────────────────────────────────────────────────

    @api.depends('rental_start', 'rental_end', 'rate_type')
    def _compute_duration(self):
        for rec in self:
            if rec.rate_type == 'fixed' or not rec.rental_start or not rec.rental_end:
                rec.rental_duration = 1.0
                continue
            delta = (rec.rental_end - rec.rental_start).days + 1
            if delta <= 0:
                rec.rental_duration = 0.0
                continue
            if rec.rate_type == 'daily':
                rec.rental_duration = float(delta)
            elif rec.rate_type == 'weekly':
                rec.rental_duration = round(delta / 7.0, 2)
            else:  # monthly
                rec.rental_duration = round(delta / 30.0, 2)

    @api.depends('rental_duration', 'rate_amount', 'rate_type')
    def _compute_revenue(self):
        for rec in self:
            rec.revenue = rec.rental_duration * rec.rate_amount

    @api.onchange('asset_register_id')
    def _onchange_asset_register_id(self):
        if self.asset_register_id:
            self.equipment_name = self.asset_register_id.name
            cat_map = {'vehicle': 'vehicle'}
            self.equipment_category = cat_map.get(
                self.asset_register_id.category, 'other'
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'way4tech.equipment.rental'
                ) or _('New')
        return super().create(vals_list)

    # ── State Actions ─────────────────────────────────────────────────────────

    def action_confirm(self):
        self.ensure_one()
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

    # ── Invoice Action ────────────────────────────────────────────────────────

    def action_create_invoice(self):
        self.ensure_one()
        if not self.revenue:
            raise UserError(_(
                'Rental revenue is zero. Please set the rate / price and dates first.'
            ))
        if self.invoice_id:
            raise UserError(_('A customer invoice already exists for this rental.'))

        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)
        analytic = self.analytic_account_id or settings.default_analytic_account_id

        # KSA 15% VAT on all customer invoices
        vat_tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('amount_type', '=', 'percent'),
            ('amount', '=', 15.0),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        # Build a descriptive invoice line name
        if self.rate_type == 'fixed':
            duration_str = ''
        else:
            unit = {'daily': 'day(s)', 'weekly': 'week(s)', 'monthly': 'month(s)'}.get(
                self.rate_type, ''
            )
            duration_str = ' — %.2f %s × SAR %.2f' % (
                self.rental_duration, unit, self.rate_amount
            )
        period_str = ''
        if self.rental_start:
            period_str = ' [%s' % self.rental_start.strftime('%d/%m/%Y')
            if self.rental_end:
                period_str += ' – %s]' % self.rental_end.strftime('%d/%m/%Y')
            else:
                period_str += ']'

        invoice_line_vals = {
            'name': 'Equipment Rental — %s%s%s / %s' % (
                self.equipment_name, duration_str, period_str, self.name,
            ),
            'quantity': 1.0,
            'price_unit': self.revenue,
        }
        # Use dedicated rental account; fall back to truck revenue account
        income_account = settings.rental_income_account_id or settings.truck_revenue_account_id
        if income_account:
            invoice_line_vals['account_id'] = income_account.id
        if analytic:
            invoice_line_vals['analytic_distribution'] = {str(analytic.id): 100}
        if vat_tax:
            invoice_line_vals['tax_ids'] = [(6, 0, [vat_tax.id])]

        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.client_id.id,
            'invoice_date': fields.Date.today(),
            'company_id': self.company_id.id,
            'invoice_line_ids': [(0, 0, invoice_line_vals)],
        }
        rental_journal = settings.rental_journal_id or settings.truck_trip_journal_id
        if rental_journal:
            invoice_vals['journal_id'] = rental_journal.id

        _category = self.env.ref('way4tech_logistics.category_others', raise_if_not_found=False)
        if _category:
            invoice_vals['way4tech_category_id'] = _category.id
        invoice = self.env['account.move'].create(invoice_vals)
        self.write({'invoice_id': invoice.id})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Rental Invoice'),
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_('No invoice linked to this rental.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Rental Invoice'),
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
