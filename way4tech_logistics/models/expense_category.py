# -*- coding: utf-8 -*-
"""Expense Category — canonical 15-item taxonomy used across:
  * Project Expenses tab (was a Selection with 6 values)
  * Project Budget tab (Budget vs Actual)
  * Payroll & Accounting Setup (per-category default GL expense account)

Making this a Many2one to a real model (instead of a Selection) lets the
list expand without a code change AND lets each category carry its own
default expense account, name (translatable), and sequence.
"""
from odoo import fields, models


class Way4TechExpenseCategory(models.Model):
    _name = "way4tech.expense.category"
    _description = "Way4Tech Expense Category (15-item KSA taxonomy)"
    _order = "sequence, name"

    name = fields.Char(string="Name", required=True, translate=True)
    code = fields.Char(string="Code", required=True, index=True)
    sequence = fields.Integer(default=10)
    default_expense_account_id = fields.Many2one(
        "account.account",
        string="Default Expense Account",
        help="GL account used by default when this category is picked on a "
             "Project Expense or Project Budget line. Fallback if the payroll "
             "settings don't map an account for this code.",
    )
    active = fields.Boolean(default=True)
