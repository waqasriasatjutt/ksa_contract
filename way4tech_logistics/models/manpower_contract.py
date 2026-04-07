from odoo import api, fields, models, _
from odoo.exceptions import UserError


class Way4TechManpowerContract(models.Model):
    _name = 'way4tech.manpower.contract'
    _description = 'Manpower Billing Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'start_date desc, name'

    name = fields.Char(string='Contract Name', required=True, tracking=True)
    client_id = fields.Many2one(
        comodel_name='res.partner',
        string='Client',
        required=True,
        tracking=True,
    )
    salesperson_id = fields.Many2one('res.users', string='Salesperson', tracking=True)
    contract_type = fields.Selection(
        selection=[
            ('food_delivery', 'Food Delivery'),
            ('project', 'Project Based'),
        ],
        string='Contract Type',
        default='project',
        tracking=True,
    )
    billing_type = fields.Selection(
        selection=[
            ('fixed', 'Fixed Price'),
            ('hourly', 'Hourly Rate'),
        ],
        string='Billing Type',
        default='fixed',
        tracking=True,
    )
    fixed_amount = fields.Monetary(
        string='Fixed Monthly Amount',
        currency_field='currency_id',
    )
    hourly_rate = fields.Monetary(
        string='Hourly Rate',
        currency_field='currency_id',
    )
    start_date = fields.Date(string='Start Date', required=True)
    end_date = fields.Date(string='End Date')
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
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
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('active', 'Active'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        tracking=True,
        copy=False,
    )
    line_ids = fields.One2many(
        comodel_name='way4tech.manpower.contract.line',
        inverse_name='contract_id',
        string='Assigned Manpower',
    )
    timesheet_ids = fields.One2many(
        comodel_name='way4tech.manpower.timesheet',
        inverse_name='contract_id',
        string='Timesheets',
    )
    invoice_ids = fields.Many2many(
        comodel_name='account.move',
        string='Invoices',
    )
    invoice_count = fields.Integer(
        string='Invoice Count',
        compute='_compute_invoice_count',
    )
    total_hours = fields.Float(
        string='Total Hours',
        compute='_compute_totals',
        store=True,
    )
    total_invoiced = fields.Monetary(
        string='Total Invoiced',
        compute='_compute_invoice_count',
        currency_field='currency_id',
    )
    total_employee_cost = fields.Monetary(
        string='Total Employee Cost',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
        help="Sum of Hours × Employee Rate across all timesheet lines. "
             "The same timesheets that drive the client invoice also drive this salary cost.",
    )
    billing_margin = fields.Monetary(
        string='Billing Margin (Hours)',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
        help="Invoiced amount minus total employee salary cost from timesheets. "
             "Positive = company earns above the labour cost on hourly contracts.",
    )
    project_expense_ids = fields.One2many(
        comodel_name='way4tech.manpower.project.expense',
        inverse_name='contract_id',
        string='Project Expenses',
    )
    total_project_expenses = fields.Monetary(
        string='Total Project Expenses',
        compute='_compute_project_margin',
        store=True,
        currency_field='currency_id',
        help='Sum of all project expense amounts (wages, accommodation, utilities, '
             'furniture, transport, other). Used to calculate project margin.',
    )
    project_margin = fields.Monetary(
        string='Project Margin',
        compute='_compute_project_margin',
        store=True,
        currency_field='currency_id',
        help='Project Margin = Total Invoiced − Total Project Expenses.\n'
             'Positive = profitable. Shows the gross margin before company overhead.\n'
             'For full P&L including individual salary costs, see the Analytic Report.',
    )
    notes = fields.Text(string='Notes')

    @api.onchange('client_id')
    def _onchange_client_id(self):
        """Auto-fill analytic from food delivery partner for per-partner profit tracking."""
        if self.client_id and not self.analytic_account_id:
            analytic = self.env['account.analytic.account'].search([
                ('partner_id', '=', self.client_id.id),
            ], limit=1)
            if analytic:
                self.analytic_account_id = analytic

    @api.depends('invoice_ids', 'invoice_ids.amount_untaxed')
    def _compute_invoice_count(self):
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids)
            rec.total_invoiced = sum(rec.invoice_ids.mapped('amount_untaxed'))

    @api.depends('timesheet_ids.hours', 'timesheet_ids.employee_cost',
                 'invoice_ids', 'invoice_ids.amount_untaxed')
    def _compute_totals(self):
        for rec in self:
            rec.total_hours = sum(rec.timesheet_ids.mapped('hours'))
            rec.total_employee_cost = sum(rec.timesheet_ids.mapped('employee_cost'))
            invoiced = sum(rec.invoice_ids.mapped('amount_untaxed'))
            rec.billing_margin = invoiced - rec.total_employee_cost

    @api.depends('project_expense_ids.amount', 'total_invoiced')
    def _compute_project_margin(self):
        for rec in self:
            rec.total_project_expenses = sum(rec.project_expense_ids.mapped('amount'))
            rec.project_margin = rec.total_invoiced - rec.total_project_expenses

    def action_activate(self):
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

    def action_create_invoice(self):
        self.ensure_one()
        if self.billing_type == 'fixed':
            amount = self.fixed_amount
            description = 'Fixed Price - %s' % self.name
        else:
            amount = self.total_hours * self.hourly_rate
            description = 'Hourly Rate (%s hrs x %s) - %s' % (
                self.total_hours, self.hourly_rate, self.name
            )

        if not amount:
            raise UserError(_('Invoice amount is zero. Please check the fixed amount or timesheet hours.'))

        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)
        analytic = self.analytic_account_id or settings.default_analytic_account_id

        # Find the default 15% VAT sales tax for this company
        vat_tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('amount_type', '=', 'percent'),
            ('amount', '=', 15.0),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        invoice_line_vals = {
            'name': description,
            'quantity': 1.0,
            'price_unit': amount,
        }
        if settings.manpower_income_account_id:
            invoice_line_vals['account_id'] = settings.manpower_income_account_id.id
        if analytic:
            invoice_line_vals['analytic_distribution'] = {str(analytic.id): 100}
        if not vat_tax:
            raise UserError(_('No 15% sales tax found for this company. Please configure a 15% VAT sales tax before creating a manpower invoice.'))
        invoice_line_vals['tax_ids'] = [(6, 0, [vat_tax.id])]

        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.client_id.id,
            'invoice_date': fields.Date.today(),
            'company_id': self.company_id.id,
            'invoice_line_ids': [(0, 0, invoice_line_vals)],
        }
        if settings.manpower_journal_id:
            invoice_vals['journal_id'] = settings.manpower_journal_id.id

        _category = self.env.ref('way4tech_logistics.category_manpower_revenue', raise_if_not_found=False)
        if _category:
            invoice_vals['way4tech_category_id'] = _category.id
        invoice = self.env['account.move'].create(invoice_vals)
        self.invoice_ids = [(4, invoice.id)]
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.invoice_ids.ids)],
        }


class Way4TechManpowerContractLine(models.Model):
    _name = 'way4tech.manpower.contract.line'
    _description = 'Manpower Contract Line'
    _order = 'contract_id, employee_id'

    contract_id = fields.Many2one(
        comodel_name='way4tech.manpower.contract',
        string='Contract',
        required=True,
        ondelete='cascade',
    )
    employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Employee',
    )
    role = fields.Char(string='Role/Position')
    start_date = fields.Date(string='Start Date')
    end_date = fields.Date(string='End Date')
    daily_cost = fields.Monetary(
        string='Daily Cost',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='contract_id.company_id.currency_id',
        string='Currency',
        readonly=True,
    )


