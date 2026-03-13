# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class RiderPayrollLine(models.Model):
    _name = 'rider.payroll.line'
    _description = 'Rider Payroll Line'
    _order = 'batch_id, sequence, name'

    sequence = fields.Integer(string='Sequence', default=10)
    batch_id = fields.Many2one(
        comodel_name='rider.payroll.batch',
        string='Payroll Batch',
        required=True,
        ondelete='cascade',
        index=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='batch_id.company_id',
        store=True,
        readonly=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='batch_id.currency_id',
        readonly=True,
    )
    name = fields.Char(
        string='Rider Name',
        required=True,
    )
    rider_type = fields.Selection(
        selection=[
            ('employee', 'Company Rider (Employee)'),
            ('freelancer', 'Freelancer (Vendor)'),
        ],
        string='Rider Type',
        required=True,
        default='employee',
    )
    employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Employee',
        check_company=True,
        help='Link to HR employee record (for company riders)',
    )
    vendor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Vendor Partner',
        domain=[('is_company', '=', False)],
        help='Vendor partner record for freelancer (used to create vendor bill)',
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        check_company=True,
        help='Override batch analytic account for this specific rider',
    )

    # Earnings
    fixed_salary = fields.Monetary(string='Fixed Salary', default=0.0)
    order_earnings = fields.Monetary(string='Order Earnings', default=0.0)
    bonus = fields.Monetary(string='Bonus', default=0.0)
    petrol = fields.Monetary(string='Petrol Allowance', default=0.0)

    # Deductions
    deduction = fields.Monetary(string='Deduction', default=0.0)
    advance_deduction = fields.Monetary(string='Advance Deduction', default=0.0)
    fine = fields.Monetary(string='Fine', default=0.0)

    # Computed
    gross_earnings = fields.Monetary(
        string='Gross Earnings',
        compute='_compute_net_payable',
        store=True,
    )
    total_deductions = fields.Monetary(
        string='Total Deductions',
        compute='_compute_net_payable',
        store=True,
    )
    net_payable = fields.Monetary(
        string='Net Payable',
        compute='_compute_net_payable',
        store=True,
    )
    has_error = fields.Boolean(
        string='Has Error',
        compute='_compute_net_payable',
        store=True,
    )

    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('validated', 'Validated'),
            ('posted', 'Posted'),
        ],
        string='Status',
        default='draft',
        required=True,
    )
    note = fields.Char(string='Note')

    @api.depends('fixed_salary', 'order_earnings', 'bonus', 'petrol',
                 'deduction', 'advance_deduction', 'fine')
    def _compute_net_payable(self):
        for line in self:
            line.gross_earnings = line.fixed_salary + line.order_earnings + line.bonus + line.petrol
            line.total_deductions = line.deduction + line.advance_deduction + line.fine
            line.net_payable = line.gross_earnings - line.total_deductions
            line.has_error = line.net_payable < 0

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        if self.employee_id:
            self.name = self.employee_id.name
            self.rider_type = 'employee'

    @api.onchange('vendor_id')
    def _onchange_vendor_id(self):
        if self.vendor_id:
            self.name = self.vendor_id.name
            self.rider_type = 'freelancer'

    @api.onchange('rider_type')
    def _onchange_rider_type(self):
        if self.rider_type == 'employee':
            self.vendor_id = False
        elif self.rider_type == 'freelancer':
            self.employee_id = False

    @api.constrains('rider_type', 'net_payable')
    def _check_rider_data(self):
        for line in self:
            if line.net_payable < 0:
                raise ValidationError(
                    _('Net payable for rider "%s" cannot be negative (%.2f). '
                      'Please review the deductions.') % (line.name, line.net_payable)
                )
