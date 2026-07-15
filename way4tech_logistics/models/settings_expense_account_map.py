# -*- coding: utf-8 -*-
"""Per-category GL account mapping for the 15 KSA expense categories.

Kept as a separate model so it's One2many-editable on the Payroll &
Accounting Setup form without inflating the parent record with 15 static
Many2one fields.
"""
from odoo import fields, models


class Way4TechSettingsExpenseAccountMap(models.Model):
    _name = "way4tech.settings.expense.account.map"
    _description = "Settings: Expense Category → GL Account Map"
    _order = "category_id"

    settings_id = fields.Many2one(
        "way4tech.payroll.settings", string="Settings", required=True, ondelete="cascade",
    )
    category_id = fields.Many2one(
        "way4tech.expense.category", string="Category", required=True,
    )
    account_id = fields.Many2one(
        "account.account", string="Expense Account",
        check_company=True, required=True,
    )
    company_id = fields.Many2one(related="settings_id.company_id", store=True, readonly=True)

    _sql_constraints = [(
        "settings_category_unique",
        "unique(settings_id, category_id)",
        "Each expense category can be mapped only once per settings record.",
    )]
