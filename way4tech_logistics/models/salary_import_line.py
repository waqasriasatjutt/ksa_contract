from odoo import api, fields, models


class SalaryImportLine(models.Model):
    _name = 'way4tech.salary.import.line'
    _description = 'Worker Salary Import Line'
    _order = 'import_id, sequence, id'

    import_id = fields.Many2one(
        comodel_name='way4tech.salary.import',
        string='Salary Import',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(string='Sequence', default=10)

    # ── Employee identification ───────────────────────────────────────────────
    employee_name = fields.Char(string='Employee Name')
    employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Employee',
    )
    # ── Platform & work data ─────────────────────────────────────────────────
    platform_id = fields.Many2one(
        comodel_name='way4tech.platform.config',
        string='Platform',
        help='Salary rules for this platform (Hungerstation, Keeta, etc.).',
    )
    valid_days = fields.Integer(
        string='Valid Days Worked',
        help='Number of valid working days the rider completed this month.',
    )
    orders_completed = fields.Integer(
        string='Orders Completed',
        help='Actual orders delivered this month.',
    )

    # ── Computed salary components ────────────────────────────────────────────
    fixed_salary = fields.Float(
        string='Basic Salary',
        digits=(16, 2),
        help='Auto-computed from platform rules, or enter manually if no platform set.',
    )
    order_adjustment = fields.Float(
        string='Order Adjustment',
        digits=(16, 2),
        help='Positive = bonus (excess orders); Negative = deduction (short orders). '
             'Auto-computed from platform rules.',
    )
    bonus = fields.Float(string='Bonus', digits=(16, 2))
    petrol_allowance = fields.Float(
        string='Petrol Allowance',
        digits=(16, 2),
        help='Company-paid petrol reimbursement (earning, not deduction).',
    )

    # ── Performance deductions ────────────────────────────────────────────────
    on_time_deduction = fields.Float(
        string='On-Time Deduction', digits=(16, 2),
    )
    food_damage_deduction = fields.Float(
        string='Food Damage Deduction', digits=(16, 2),
    )
    miss_day_penalty = fields.Float(
        string='Miss Day Penalty', digits=(16, 2),
    )
    order_rejection_deduction = fields.Float(
        string='Order Rejection Deduction', digits=(16, 2),
    )
    misc_deduction = fields.Float(
        string='Misc Deduction', digits=(16, 2),
    )

    # ── Office / ledger deductions ────────────────────────────────────────────
    advance_deduction = fields.Float(
        string='Advance', digits=(16, 2),
    )
    fuel_deduction = fields.Float(
        string='Fuel', digits=(16, 2),
        help='Fuel charged to the rider (deduction).',
    )
    sim_charges = fields.Float(
        string='SIM Charges', digits=(16, 2),
    )
    loan = fields.Float(
        string='Loan', digits=(16, 2),
    )
    loan_balance_before = fields.Float(
        string='Loan Balance Before',
        digits=(16, 2),
        help='Outstanding loan balance BEFORE this month\'s installment deduction. '
             'Auto-filled from the Deductions Ledger when importing or clicking "Fill from Ledger".',
    )
    loan_balance_after = fields.Float(
        string='Loan Remaining',
        compute='_compute_loan_balance_after',
        store=True,
        digits=(16, 2),
        help='Remaining loan balance AFTER this month\'s installment: Balance Before − Loan Installment.',
    )
    traffic_violation = fields.Float(
        string='Traffic Violation', digits=(16, 2),
    )
    rent = fields.Float(
        string='Rent', digits=(16, 2),
    )

    # ── Computed totals ───────────────────────────────────────────────────────
    gross_earnings = fields.Float(
        string='Gross Earnings',
        compute='_compute_totals',
        store=True,
        digits=(16, 2),
    )
    total_performance_deduction = fields.Float(
        string='Performance Deductions',
        compute='_compute_totals',
        store=True,
        digits=(16, 2),
    )
    total_office_deduction = fields.Float(
        string='Office Deductions',
        compute='_compute_totals',
        store=True,
        digits=(16, 2),
    )
    total_deductions = fields.Float(
        string='Total Deductions',
        compute='_compute_totals',
        store=True,
        digits=(16, 2),
    )
    net_payable = fields.Float(
        string='Net Payable',
        compute='_compute_totals',
        store=True,
        digits=(16, 2),
    )

    # ── Status ────────────────────────────────────────────────────────────────
    has_error = fields.Boolean(string='Has Error', default=False)
    error_message = fields.Char(string='Error Message')
    note = fields.Char(string='Note')

    # ── Compute totals ────────────────────────────────────────────────────────
    @api.depends(
        'fixed_salary', 'order_adjustment', 'bonus', 'petrol_allowance',
        'on_time_deduction', 'food_damage_deduction', 'miss_day_penalty',
        'order_rejection_deduction', 'misc_deduction',
        'advance_deduction', 'fuel_deduction', 'sim_charges',
        'loan', 'traffic_violation', 'rent',
    )
    def _compute_totals(self):
        for line in self:
            order_bonus = max(line.order_adjustment, 0.0)
            order_penalty = abs(min(line.order_adjustment, 0.0))

            gross = (
                line.fixed_salary
                + order_bonus
                + line.bonus
                + line.petrol_allowance
            )
            perf_deduct = (
                line.on_time_deduction
                + line.food_damage_deduction
                + line.miss_day_penalty
                + line.order_rejection_deduction
                + line.misc_deduction
                + order_penalty
            )
            office_deduct = (
                line.advance_deduction
                + line.fuel_deduction
                + line.sim_charges
                + line.loan
                + line.traffic_violation
                + line.rent
            )
            total_deduct = perf_deduct + office_deduct
            line.gross_earnings = gross
            line.total_performance_deduction = perf_deduct
            line.total_office_deduction = office_deduct
            line.total_deductions = total_deduct
            line.net_payable = gross - total_deduct

    @api.depends('loan_balance_before', 'loan')
    def _compute_loan_balance_after(self):
        for line in self:
            line.loan_balance_after = max(0.0, line.loan_balance_before - line.loan)

    # ── Auto-compute salary from platform rules ───────────────────────────────
    @api.onchange('platform_id', 'valid_days', 'orders_completed')
    def _onchange_platform_salary(self):
        if self.platform_id and (self.valid_days or self.orders_completed):
            basic, adjustment = self.platform_id.compute_salary(
                self.valid_days or 0,
                self.orders_completed or 0,
            )
            self.fixed_salary = basic
            self.order_adjustment = adjustment

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id:
            self.employee_name = self.employee_id.name

    def action_compute_salary(self):
        """Manual trigger: recompute fixed_salary and order_adjustment from platform rules."""
        for line in self:
            if line.platform_id:
                basic, adjustment = line.platform_id.compute_salary(
                    line.valid_days or 0,
                    line.orders_completed or 0,
                )
                line.fixed_salary = basic
                line.order_adjustment = adjustment
