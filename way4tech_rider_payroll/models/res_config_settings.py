# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    rider_payroll_salary_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Default Salary Expense Account',
        related='company_id.rider_payroll_salary_account_id',
        readonly=False,
        domain=[('account_type', 'in', ['expense', 'expense_direct_cost'])],
    )
    rider_payroll_salary_payable_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Default Salary Payable Account',
        related='company_id.rider_payroll_salary_payable_account_id',
        readonly=False,
        domain=[('account_type', 'in', ['liability_current', 'liability_payable'])],
    )
    rider_payroll_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Default Payroll Journal',
        related='company_id.rider_payroll_journal_id',
        readonly=False,
        domain=[('type', 'in', ['general', 'purchase'])],
    )


class ResCompany(models.Model):
    _inherit = 'res.company'

    rider_payroll_salary_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Default Salary Expense Account',
        check_company=True,
    )
    rider_payroll_salary_payable_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Default Salary Payable Account',
        check_company=True,
    )
    rider_payroll_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Default Payroll Journal',
        check_company=True,
    )
