# -*- coding: utf-8 -*-
"""Expense Category — canonical KSA taxonomy used across:
  * Project Expenses tab (was a Selection with 6 values)
  * Project Budget tab (Budget vs Actual)
  * Payroll & Accounting Setup (per-category default GL expense account)

CR2 G2 (19.0.2.6.0): each category is bucketed into `expense_type`
('direct' | 'operating'). The Manpower Contract splits its Project Expenses
notebook page into two tabs, one per bucket, and the Billing Summary CGS/OpEx
split is now driven by this field (not by account.account.account_type).
"""
from odoo import fields, models


class Way4TechExpenseCategory(models.Model):
    _name = "way4tech.expense.category"
    _description = "Way4Tech Expense Category (KSA taxonomy)"
    _order = "expense_type, sequence, name"

    name = fields.Char(string="Name", required=True, translate=True)
    code = fields.Char(string="Code", required=True, index=True)
    sequence = fields.Integer(default=10)
    expense_type = fields.Selection(
        selection=[
            ('direct', 'Direct Cost'),
            ('operating', 'Operating Exp'),
        ],
        string='Expense Bucket',
        required=True,
        default='operating',
        help="Which Project Expense tab this category feeds on a Manpower "
             "Contract:\n"
             "  Direct Cost — worker wages, client commission, transportation, "
             "equipment rent, building rent, utility exp. Bills are treated as "
             "COGS on the Billing Summary and require a customer invoice on "
             "the parent contract before they can be posted.\n"
             "  Operating Exp — everything else. Bills post to OpEx and can be "
             "created independently of customer invoicing.",
    )
    default_expense_account_id = fields.Many2one(
        "account.account",
        string="Default Expense Account",
        help="GL account used by default when this category is picked on a "
             "Project Expense or Project Budget line. Fallback if the payroll "
             "settings don't map an account for this code.",
    )
    active = fields.Boolean(default=True)
