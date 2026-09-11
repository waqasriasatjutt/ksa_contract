# -*- coding: utf-8 -*-
"""Per-category GL account mapping for the KSA expense categories.

Kept as a separate model so it's One2many-editable on the Payroll &
Accounting Setup form without inflating the parent record with static
Many2one fields per category.

CR2 G2 (19.0.2.6.0): each row now also carries an Input VAT tax so vendor
bills created from Project Expense lines apply the correct purchase-side
tax automatically. The client uses the label "Input VAT Account" but Odoo
models VAT as an ``account.tax`` record whose invoice-repartition posts
the input-VAT amount to the correct GL account.
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
    category_expense_type = fields.Selection(
        related="category_id.expense_type", string="Bucket", store=False, readonly=True,
    )
    account_id = fields.Many2one(
        "account.account", string="Expense Account",
        check_company=True, required=True,
    )
    input_vat_tax_id = fields.Many2one(
        "account.tax",
        string="Input VAT Account",
        check_company=True,
        domain="[('type_tax_use', '=', 'purchase'), ('company_id', '=', company_id)]",
        help="Purchase-side VAT tax applied to vendor bills generated from "
             "Project Expense lines in this category. Client terminology is "
             "'Input VAT Account' — in Odoo this is an account.tax record "
             "whose invoice-repartition posts the input VAT amount to the "
             "correct GL account. Leave empty to skip VAT on this category "
             "(Operating Exp only; Direct Cost raises UserError if unset).",
    )
    company_id = fields.Many2one(related="settings_id.company_id", store=True, readonly=True)

    _settings_category_unique = models.Constraint(
        "unique(settings_id, category_id)",
        "Each expense category can be mapped only once per settings record.",
    )
