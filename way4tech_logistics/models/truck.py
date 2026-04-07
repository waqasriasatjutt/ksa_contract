from odoo import api, fields, models, _
from odoo.exceptions import UserError


class Way4TechInvestorPayable(models.Model):
    _name = 'way4tech.investor.payable'
    _description = 'Investor Payable'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'period_start desc, name desc'

    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default=lambda self: _('New'),
    )
    truck_id = fields.Many2one(
        comodel_name='fleet.vehicle',
        string='Truck / Vehicle',
        required=True,
        tracking=True,
    )
    ownership_type = fields.Selection(
        related='truck_id.ownership_type',
        store=True,
        readonly=True,
    )
    investor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Investor',
        related='truck_id.investor_id',
        store=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
        store=True,
    )
    period_start = fields.Date(string='Period Start', required=True)
    period_end = fields.Date(string='Period End', required=True)
    total_revenue = fields.Monetary(
        string='Total Revenue from Client',
        currency_field='currency_id',
    )
    total_expenses = fields.Monetary(
        string='Direct Expenses (Driver + Fuel + Maintenance)',
        currency_field='currency_id',
        help="Sum of trip direct costs (driver salary, overtime, fuel) and maintenance costs for the period.",
    )
    gross_profit = fields.Monetary(
        string='Gross Profit',
        compute='_compute_amounts', store=True,
        currency_field='currency_id',
        help="Revenue − Direct Expenses. This is the amount split between investor and company.",
    )
    profit_share_rate = fields.Float(
        string='Investor Share %',
        related='truck_id.profit_share_rate',
        store=True,
        digits=(5, 2),
    )
    investor_amount = fields.Monetary(
        string='Investor Share',
        compute='_compute_amounts', store=True,
        currency_field='currency_id',
        help="Gross Profit × Investor Share %",
    )
    company_gross = fields.Monetary(
        string='Company Gross Share',
        compute='_compute_amounts', store=True,
        currency_field='currency_id',
        help="Gross Profit × (100% − Investor Share %). Company bears all indirect expenses from this amount.",
    )
    # ── Indirect / Operational Expenses (borne by company only) ──────────────
    yard_rent = fields.Monetary(
        string='Yard Rent (Parking)', currency_field='currency_id',
        help="Monthly parking/yard rent allocated to this truck.",
    )
    coordinator_salary = fields.Monetary(
        string='Coordinator Salary', currency_field='currency_id',
        help="Coordinator/logistics staff salary allocated to this truck.",
    )
    iqama_cost = fields.Monetary(
        string='Iqama / Visa Cost', currency_field='currency_id',
        help="Driver and coordinator iqama renewal cost allocated to this truck.",
    )
    other_operational = fields.Monetary(
        string='Other Operational Expenses', currency_field='currency_id',
    )
    total_indirect = fields.Monetary(
        string='Total Indirect Expenses',
        compute='_compute_amounts', store=True,
        currency_field='currency_id',
        help="Yard Rent + Coordinator Salary + Iqama + Other. Borne by company only.",
    )
    company_net = fields.Monetary(
        string='Company Net Profit',
        compute='_compute_amounts', store=True,
        currency_field='currency_id',
        help="Company Gross Share − Total Indirect Expenses.",
    )
    # Kept for backward compatibility
    net_profit = fields.Monetary(
        string='Net Profit (Gross)',
        compute='_compute_amounts', store=True,
        currency_field='currency_id',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('paid', 'Paid'),
        ],
        string='Status',
        default='draft',
        tracking=True,
        copy=False,
    )
    bill_id = fields.Many2one(
        comodel_name='account.move',
        string='Vendor Bill',
        readonly=True,
        copy=False,
    )
    payment_date = fields.Date(string='Payment Date')
    notes = fields.Text(string='Notes')

    @api.depends(
        'total_revenue', 'total_expenses', 'profit_share_rate', 'ownership_type',
        'yard_rent', 'coordinator_salary', 'iqama_cost', 'other_operational',
    )
    def _compute_amounts(self):
        for rec in self:
            gross = rec.total_revenue - rec.total_expenses
            if rec.ownership_type == 'investor':
                investor = gross * rec.profit_share_rate / 100.0
            else:
                investor = 0.0
            company_gross = gross - investor
            indirect = (
                rec.yard_rent + rec.coordinator_salary
                + rec.iqama_cost + rec.other_operational
            )
            rec.gross_profit = gross
            rec.net_profit = gross              # backward compat alias
            rec.investor_amount = investor
            rec.company_gross = company_gross
            rec.total_indirect = indirect
            rec.company_net = company_gross - indirect

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'way4tech.investor.payable'
                ) or _('New')
        return super().create(vals_list)

    def action_compute_from_trips(self):
        """
        Auto-aggregate confirmed/done trip revenues and all costs for the period.

        total_revenue  = sum of trip revenues
        total_expenses = trip operational costs (fuel + driver + other per trip)
                       + maintenance costs (from truck.maintenance records)
        """
        self.ensure_one()
        if not self.period_start or not self.period_end:
            raise UserError(_('Please set Period Start and Period End before computing.'))

        trips = self.env['way4tech.truck.trip'].search([
            ('truck_id', '=', self.truck_id.id),
            ('trip_date', '>=', self.period_start),
            ('trip_date', '<=', self.period_end),
            ('state', 'in', ('confirmed', 'done')),
        ])
        maintenances = self.env['fleet.vehicle.log.services'].search([
            ('vehicle_id', '=', self.truck_id.id),
            ('date', '>=', self.period_start),
            ('date', '<=', self.period_end),
            ('way4tech_state', 'in', ('confirmed', 'done')),
        ])
        trip_operational_costs = sum(trips.mapped('total_cost'))   # fuel+driver+other
        maintenance_costs = sum(maintenances.mapped('amount'))
        self.write({
            'total_revenue': sum(trips.mapped('revenue')),
            'total_expenses': trip_operational_costs + maintenance_costs,
        })

    def action_confirm(self):
        self.ensure_one()
        self.state = 'confirmed'

    def action_create_bill(self):
        self.ensure_one()
        if self.truck_id.ownership_type != 'investor':
            raise UserError(_('Vendor bills are only created for investor-owned vehicles. This is a company-owned vehicle.'))
        if self.state == 'draft':
            self.action_confirm()
        if not self.investor_id:
            raise UserError(_('No investor linked to this truck. Please set an investor on the truck first.'))

        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)
        analytic = self.truck_id.analytic_account_id or settings.default_analytic_account_id

        bill_line_vals = {
            'name': 'Investor Profit Share - ' + self.name,
            'quantity': 1.0,
            'price_unit': self.investor_amount,
        }
        if settings.investor_payable_account_id:
            bill_line_vals['account_id'] = settings.investor_payable_account_id.id
        if analytic:
            bill_line_vals['analytic_distribution'] = {str(analytic.id): 100}

        inv_category = self.env.ref('way4tech_logistics.category_commission', raise_if_not_found=False)
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.investor_id.id,
            'invoice_date': fields.Date.today(),
            'company_id': self.company_id.id,
            'invoice_line_ids': [(0, 0, bill_line_vals)],
        }
        if inv_category:
            bill_vals['way4tech_category_id'] = inv_category.id
        bill = self.env['account.move'].create(bill_vals)
        self.write({'bill_id': bill.id})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_reset_draft(self):
        self.ensure_one()
        self.state = 'draft'

    def action_view_bill(self):
        self.ensure_one()
        if not self.bill_id:
            raise UserError(_('No vendor bill linked to this record.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'res_id': self.bill_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    @api.model
    def _auto_generate_monthly_payables(self):
        """
        Scheduled action — runs on the 1st of each month.
        Creates a draft investor payable for the previous calendar month
        for every active investor-owned truck that does not already have one.
        Automatically computes revenue and expenses from trips/maintenance.
        """
        from dateutil.relativedelta import relativedelta
        today = fields.Date.today()
        first_of_this_month = today.replace(day=1)
        period_end = first_of_this_month - relativedelta(days=1)
        period_start = period_end.replace(day=1)

        trucks = self.env['fleet.vehicle'].search([
            ('operational_state', '!=', 'inactive'),
        ])
        for truck in trucks:
            existing = self.search([
                ('truck_id', '=', truck.id),
                ('period_start', '=', period_start),
                ('period_end', '=', period_end),
            ], limit=1)
            if existing:
                continue
            payable = self.create({
                'truck_id': truck.id,
                'period_start': period_start,
                'period_end': period_end,
                'company_id': truck.company_id.id,
            })
            payable.action_compute_from_trips()
            # Remove the record if no actual activity found for the period
            if not payable.total_revenue and not payable.total_expenses:
                payable.unlink()
        return True
