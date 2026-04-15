from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class Way4TechTripProjectAllocation(models.Model):
    _name = 'way4tech.trip.project.allocation'
    _description = 'Trip Project Allocation (multi-project split)'
    _order = 'date_from'

    trip_id = fields.Many2one(
        'way4tech.truck.trip', string='Trip',
        required=True, ondelete='cascade', index=True,
    )
    project_name = fields.Char(string='Project Name', required=True)
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Analytic Account',
        help='Optional — link to an analytic account for project reporting.',
    )
    date_from = fields.Date(string='From', required=True)
    date_to = fields.Date(string='To', required=True)
    notes = fields.Char(string='Notes')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_from and rec.date_to and rec.date_from > rec.date_to:
                raise ValidationError(_('Project allocation "From" must be on or before "To".'))


class Way4TechTruckTrip(models.Model):
    _name = 'way4tech.truck.trip'
    _description = 'Truck Trip / Rental'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'trip_date desc, name desc'

    name = fields.Char(
        string='Reference', readonly=True, copy=False,
        default=lambda self: _('New'),
    )
    truck_id = fields.Many2one('fleet.vehicle', string='Truck', required=True, tracking=True)
    truck_license_plate = fields.Char(
        related='truck_id.license_plate', string='License Plate',
        store=True, readonly=True,
    )
    client_id = fields.Many2one('res.partner', string='Client', required=True, tracking=True)
    salesperson_id = fields.Many2one('res.users', string='Salesperson', tracking=True)
    trip_date = fields.Date(
        string='Trip Date', required=True, default=fields.Date.today, tracking=True,
    )
    trip_type = fields.Selection(
        selection=[
            ('delivery', 'Delivery'),
            ('rental', 'Rental'),
            ('flatbed', 'Flatbed (Fixed Rate)'),
            ('middleman', 'Middleman (3rd-Party Hired → Client)'),
            ('yard_rental', 'Yard Rental Income'),
            ('other', 'Other'),
        ],
        string='Trip / Revenue Type', default='delivery', tracking=True,
        help='Middleman: company hires truck from 3rd-party vendor and rents to client.\n'
             'Yard Rental: company shares yard and earns rental income from the other party.',
    )
    # ── Middleman / 3rd-party cost ───────────────────────────────────────────
    third_party_vendor_id = fields.Many2one(
        'res.partner', string='3rd-Party Truck Vendor',
        domain=[('supplier_rank', '>', 0)],
        help='Vendor from whom the truck is hired (for Middleman trips).',
    )
    third_party_cost = fields.Monetary(
        string='3rd-Party Hire Cost',
        currency_field='currency_id',
        help='Amount paid to the 3rd-party vendor for this trip (Middleman trips).',
    )
    origin = fields.Char(string='Origin')
    destination = fields.Char(string='Destination')
    distance_km = fields.Float(string='Distance (km)', digits=(10, 2))

    # ── Client PO link ────────────────────────────────────────────────────────
    po_id = fields.Many2one(
        'way4tech.client.po', string='Client PO',
        domain="[('client_id', '=', client_id), ('state', '!=', 'closed')]",
        tracking=True,
        help="Link this trip to a client Purchase Order for balance tracking.",
    )

    # ── Revenue Calculation Basis ─────────────────────────────────────────────
    rental_type = fields.Selection(
        selection=[
            ('manual', 'Manual Entry'),
            ('hours', 'Hours × Rate (Standard + Overtime)'),
            ('per_trip', 'Per Trip × Rate'),
            ('flat', 'Fixed Monthly / Flat Rate'),
        ],
        string='Revenue Basis', default='manual', required=True,
        help="How the revenue for this trip is calculated.\n"
             "• Manual: enter the revenue amount directly.\n"
             "• Hours × Rate: standard hours + overtime hours × respective rates.\n"
             "• Per Trip × Rate: number of trips × agreed rate per trip.\n"
             "• Flat Rate: fixed monthly or rental amount entered directly.",
    )
    standard_hours = fields.Float(string='Standard Hours', digits=(10, 2))
    hourly_rate = fields.Monetary(string='Hourly Rate', currency_field='currency_id')
    overtime_hours = fields.Float(string='Overtime Hours', digits=(10, 2))
    overtime_rate = fields.Monetary(string='Overtime Rate', currency_field='currency_id')
    trip_count = fields.Integer(string='No. of Trips')
    rate_per_trip = fields.Monetary(string='Rate per Trip', currency_field='currency_id')

    revenue = fields.Monetary(
        string='Revenue', currency_field='currency_id', tracking=True,
        help="Amount charged to the client. Auto-calculated when Revenue Basis is set "
             "to Hours×Rate or Per Trip×Rate. Enter manually for Manual or Flat Rate.",
    )

    # ── Driver Cost Breakdown ─────────────────────────────────────────────────
    driver_id = fields.Many2one('hr.employee', string='Driver')
    driver_iqama_number = fields.Char(
        related='driver_id.way4tech_iqama_number',
        string="Driver Iqama #",
        readonly=True,
        store=False,
    )
    driver_basic = fields.Monetary(
        string='Driver Basic Salary', currency_field='currency_id',
        help="Driver's basic monthly/trip salary portion.\n"
             "For Per Trip mode: auto-calculated as Trip Count × Driver Rate per Trip.\n"
             "For other modes: enter manually.",
    )
    driver_rate_per_trip = fields.Monetary(
        string="Driver's Rate / Trip", currency_field='currency_id',
        help="Driver's pay per completed trip. Used to auto-compute driver salary "
             "when Revenue Basis = Per Trip × Rate. The same trip count drives both "
             "the client invoice (client rate) and the driver salary (driver rate).",
    )
    driver_overtime_amount = fields.Monetary(
        string='Driver Overtime', currency_field='currency_id',
        help="Overtime pay for this trip/period.\n"
             "For Hours mode: auto-calculated as Overtime Hours × Driver OT Rate.",
    )
    driver_overtime_rate = fields.Monetary(
        string="Driver OT Rate / Hour", currency_field='currency_id',
        help="Driver's hourly overtime rate. Used to auto-compute overtime pay "
             "when Revenue Basis = Hours × Rate.",
    )
    driver_food_allowance = fields.Monetary(
        string='Food Allowance', currency_field='currency_id',
        help="Food/meal allowance paid to the driver.",
    )
    driver_cost = fields.Monetary(
        string='Driver Cost (Total)',
        compute='_compute_driver_cost', store=True,
        currency_field='currency_id',
        help="Auto-calculated: Basic Salary + Overtime + Food Allowance.",
    )

    # ── Other Direct Costs ────────────────────────────────────────────────────
    fuel_cost = fields.Monetary(string='Fuel / Diesel Cost', currency_field='currency_id')
    other_cost = fields.Monetary(string='Other Cost', currency_field='currency_id')

    total_cost = fields.Monetary(
        string='Total Direct Cost',
        compute='_compute_totals', store=True,
        currency_field='currency_id',
        help="Driver Cost + Fuel/Diesel + Other Cost.",
    )
    gross_profit = fields.Monetary(
        string='Gross Profit',
        compute='_compute_totals', store=True,
        currency_field='currency_id',
        help="Revenue − Total Direct Cost (before indirect/operational expenses).",
    )

    # ── Accounting ────────────────────────────────────────────────────────────
    invoice_id = fields.Many2one('account.move', string='Customer Invoice', readonly=True, copy=False)
    cost_move_id = fields.Many2one(
        'account.move', string='Cost Journal Entry', readonly=True, copy=False,
        help='Journal entry posting driver salary, fuel and other trip costs.',
    )
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company, required=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id',
        string='Currency', readonly=True, store=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('done', 'Done'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status', default='draft', tracking=True, copy=False,
    )
    notes = fields.Text(string='Notes')

    # ── Multi-Project Allocation (Flat Rate only) ────────────────────────────
    # Used when the same truck serves multiple projects during a rental period.
    project_allocation_ids = fields.One2many(
        'way4tech.trip.project.allocation', 'trip_id',
        string='Project Allocations',
        help="For Fixed Monthly / Flat Rate trips: allocate the period across "
             "multiple projects with their own date ranges.",
    )

    # ── Compute Methods ───────────────────────────────────────────────────────

    @api.depends('driver_basic', 'driver_overtime_amount', 'driver_food_allowance')
    def _compute_driver_cost(self):
        for rec in self:
            rec.driver_cost = (
                rec.driver_basic + rec.driver_overtime_amount + rec.driver_food_allowance
            )

    @api.depends('fuel_cost', 'driver_cost', 'other_cost', 'revenue', 'third_party_cost', 'trip_type')
    def _compute_totals(self):
        for rec in self:
            third_party = rec.third_party_cost if rec.trip_type == 'middleman' else 0.0
            rec.total_cost = rec.fuel_cost + rec.driver_cost + rec.other_cost + third_party
            rec.gross_profit = rec.revenue - rec.total_cost

    @api.onchange('truck_id')
    def _onchange_truck_autoselect_driver(self):
        """Auto-select the truck's current assigned driver (user can still override)."""
        if self.truck_id and not self.driver_id:
            current = self.truck_id.current_driver_assignment_id
            if current and current.employee_id:
                self.driver_id = current.employee_id

    @api.onchange('rental_type', 'standard_hours', 'hourly_rate',
                  'overtime_hours', 'overtime_rate', 'trip_count', 'rate_per_trip',
                  'driver_rate_per_trip', 'driver_overtime_rate')
    def _onchange_revenue_basis(self):
        if self.rental_type == 'hours':
            self.revenue = (
                (self.standard_hours * self.hourly_rate) +
                (self.overtime_hours * self.overtime_rate)
            )
            # Same overtime hours → auto-compute driver overtime pay
            if self.driver_overtime_rate:
                self.driver_overtime_amount = self.overtime_hours * self.driver_overtime_rate
        elif self.rental_type == 'per_trip':
            self.revenue = self.trip_count * self.rate_per_trip
            # Same trip count → auto-compute driver basic salary for this trip block
            if self.driver_rate_per_trip:
                self.driver_basic = self.trip_count * self.driver_rate_per_trip

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'way4tech.truck.trip'
                ) or _('New')
        return super().create(vals_list)

    # ── PO / Limit Check ──────────────────────────────────────────────────────

    def _check_po_limit(self):
        for rec in self:
            if rec.po_id:
                po = rec.po_id
                other_trips = self.env['way4tech.truck.trip'].search([
                    ('po_id', '=', po.id),
                    ('state', 'in', ('confirmed', 'done')),
                    ('id', '!=', rec.id),
                ])
                consumed = sum(other_trips.mapped('revenue'))
                remaining = po.total_amount - consumed
                if rec.revenue > remaining:
                    raise UserError(_(
                        'Trip revenue (%.2f) exceeds the remaining PO balance (%.2f).\n'
                        'PO: %s | Total: %.2f | Consumed: %.2f | Remaining: %.2f'
                    ) % (rec.revenue, remaining, po.name,
                         po.total_amount, consumed, remaining))
            elif rec.truck_id.po_limit and rec.revenue > rec.truck_id.po_limit:
                raise UserError(_(
                    'Trip revenue (%.2f) exceeds the PO limit (%.2f) on truck %s.'
                ) % (rec.revenue, rec.truck_id.po_limit, rec.truck_id.name))

    # ── State Actions ─────────────────────────────────────────────────────────

    def action_confirm(self):
        self.ensure_one()
        self._check_po_limit()
        self.state = 'confirmed'

    def action_done(self):
        self.ensure_one()
        self.state = 'done'

    def action_cancel(self):
        self.ensure_one()
        self.state = 'cancelled'

    def action_reset_draft(self):
        self.ensure_one()
        self.state = 'draft'

    # ── Invoice / Cost Entry Actions ──────────────────────────────────────────

    def action_create_invoice(self):
        self.ensure_one()
        if not self.revenue:
            raise UserError(_('Trip revenue is zero. Please enter the revenue first.'))
        if self.invoice_id:
            raise UserError(_('A customer invoice already exists for this trip.'))

        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)
        analytic = (
            self.analytic_account_id
            or self.truck_id.analytic_account_id
            or settings.default_analytic_account_id
        )
        # KSA 15% VAT on all customer invoices
        vat_tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('amount_type', '=', 'percent'),
            ('amount', '=', 15.0),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        trip_label = self.trip_type and dict(self._fields['trip_type'].selection).get(self.trip_type, '')
        invoice_line_vals = {
            'name': 'Truck Trip Revenue (%s) - %s / %s → %s' % (
                trip_label, self.name, self.origin or '', self.destination or '',
            ),
            'quantity': 1.0,
            'price_unit': self.revenue,
        }
        if settings.truck_revenue_account_id:
            invoice_line_vals['account_id'] = settings.truck_revenue_account_id.id
        if analytic:
            invoice_line_vals['analytic_distribution'] = {str(analytic.id): 100}
        if vat_tax:
            invoice_line_vals['tax_ids'] = [(6, 0, [vat_tax.id])]

        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.client_id.id,
            'invoice_date': self.trip_date,
            'company_id': self.company_id.id,
            'invoice_line_ids': [(0, 0, invoice_line_vals)],
        }
        if settings.truck_trip_journal_id:
            invoice_vals['journal_id'] = settings.truck_trip_journal_id.id

        if self.po_id:
            invoice_vals['way4tech_po_id'] = self.po_id.id
        invoice = self.env['account.move'].create(invoice_vals)
        self.write({'invoice_id': invoice.id})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Customer Invoice'),
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_('No customer invoice linked to this trip.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Customer Invoice'),
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_post_trip_costs(self):
        self.ensure_one()
        if self.state == 'cancelled':
            raise UserError(_('Cannot post costs for a cancelled trip.'))
        if self.cost_move_id:
            raise UserError(_('Trip costs have already been posted. View or reset the journal entry first.'))
        if not self.total_cost:
            raise UserError(_('No trip costs to post — all cost fields are zero.'))

        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)
        if not settings.truck_expense_account_id:
            raise UserError(_('Configure Truck Expense Account in Settings → Accounting Setup → Fleet & Trucks.'))
        if not settings.truck_costs_payable_account_id:
            raise UserError(_('Configure Truck Costs Payable Account in Settings → Accounting Setup → Fleet & Trucks.'))

        analytic = (
            self.analytic_account_id
            or self.truck_id.analytic_account_id
            or settings.default_analytic_account_id
        )
        analytic_dist = {str(analytic.id): 100} if analytic else False

        cost_items = [
            (self.driver_basic,           settings.truck_expense_account_id,  'Driver Basic Salary - %s' % self.name),
            (self.driver_overtime_amount, settings.truck_expense_account_id,  'Driver Overtime - %s' % self.name),
            (self.driver_food_allowance,  settings.truck_expense_account_id,  'Driver Food Allowance - %s' % self.name),
            (self.fuel_cost,              settings.truck_expense_account_id,  'Fuel / Diesel - %s' % self.name),
            (self.other_cost,             settings.truck_expense_account_id,  'Other Cost - %s' % self.name),
        ]
        # Middleman trips: 3rd-party hire cost → separate line (vendor payable)
        if self.trip_type == 'middleman' and self.third_party_cost:
            third_party_acct = settings.subcontractor_expense_account_id or settings.truck_expense_account_id
            cost_items.append((
                self.third_party_cost, third_party_acct,
                '3rd-Party Hire Cost (%s) - %s' % (
                    self.third_party_vendor_id.name if self.third_party_vendor_id else 'Vendor',
                    self.name,
                ),
            ))
        debit_lines = []
        for amount, account, label in cost_items:
            if amount and account:
                line = {
                    'name': label,
                    'account_id': account.id,
                    'debit': amount,
                    'credit': 0.0,
                }
                if analytic_dist:
                    line['analytic_distribution'] = analytic_dist
                debit_lines.append(line)

        if not debit_lines:
            raise UserError(_('No trip costs to post — cost amounts are zero or expense accounts are not configured.'))
        total_posted = sum(l['debit'] for l in debit_lines)
        credit_line = {
            'name': 'Trip Costs Payable - %s' % self.name,
            'account_id': settings.truck_costs_payable_account_id.id,
            'debit': 0.0,
            'credit': total_posted,
        }
        if analytic_dist:
            credit_line['analytic_distribution'] = analytic_dist

        journal = settings.truck_expense_journal_id or settings.employee_cost_journal_id
        # Resolve trip-cost category (Fuel / Diesel)
        trip_category = self.env.ref('way4tech_logistics.category_fuel', raise_if_not_found=False)

        move_vals = {
            'move_type': 'entry',
            'date': self.trip_date,
            'ref': 'Trip Costs: %s / %s' % (self.name, self.truck_id.name),
            'company_id': self.company_id.id,
            'line_ids': [(0, 0, line) for line in debit_lines] + [(0, 0, credit_line)],
        }
        if trip_category:
            move_vals['way4tech_category_id'] = trip_category.id
        if journal:
            move_vals['journal_id'] = journal.id

        move = self.env['account.move'].create(move_vals)
        move.action_post()
        self.write({'cost_move_id': move.id})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Trip Cost Journal Entry'),
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_cost_move(self):
        self.ensure_one()
        if not self.cost_move_id:
            raise UserError(_('No cost journal entry linked to this trip.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Trip Cost Journal Entry'),
            'res_model': 'account.move',
            'res_id': self.cost_move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
