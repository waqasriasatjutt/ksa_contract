from odoo import api, fields, models


class Way4TechManpowerTimesheet(models.Model):
    _name = 'way4tech.manpower.timesheet'
    _description = 'Manpower Contract Timesheet'
    _order = 'contract_id, date, id'

    contract_id = fields.Many2one(
        comodel_name='way4tech.manpower.contract',
        string='Contract',
        required=True,
        ondelete='cascade',
        index=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.today,
    )
    employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Employee',
    )
    description = fields.Char(string='Description')
    hours = fields.Float(string='Hours', digits=(16, 2))

    # ── Employee salary cost side (mirrors the billing side) ──────────────────
    employee_hourly_rate = fields.Monetary(
        string="Employee Rate / Hour",
        currency_field='currency_id',
        help="Employee's hourly salary cost. The same hours used to invoice the client "
             "also compute the employee's salary cost for this period. "
             "This is the gross salary rate (what the company pays the employee per hour).",
    )
    employee_cost = fields.Monetary(
        string='Employee Cost',
        compute='_compute_employee_cost',
        store=True,
        currency_field='currency_id',
        help="Hours × Employee Rate. The direct labour cost for this timesheet line.",
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='contract_id.company_id.currency_id',
        string='Currency',
        readonly=True,
    )

    @api.depends('hours', 'employee_hourly_rate')
    def _compute_employee_cost(self):
        for line in self:
            line.employee_cost = line.hours * line.employee_hourly_rate

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        """Auto-fill employee hourly rate from hr.employee if available."""
        if self.employee_id and not self.employee_hourly_rate:
            emp = self.employee_id
            # Try to get hourly rate from employee's contract (hr.contract)
            contract = self.env['hr.contract'].search([
                ('employee_id', '=', emp.id),
                ('state', '=', 'open'),
            ], limit=1)
            if contract and contract.wage:
                # Convert monthly wage to hourly rate (Saudi: 30 days × 8 hours)
                self.employee_hourly_rate = contract.wage / (30.0 * 8.0)
