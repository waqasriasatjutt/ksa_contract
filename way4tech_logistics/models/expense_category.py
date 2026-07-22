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
from odoo import _, api, fields, models
from odoo.exceptions import UserError

# CR3-FINAL round 3, item 10: an expense or budget line may only ever land on a
# P&L cost account. A Building Maintenance budget line silently picked up
# "120006 InterCompany Petty cash" — an asset — because the resolver fell back
# to whatever default_expense_account_id happened to hold. Anything outside this
# set is rejected rather than used.
VALID_EXPENSE_ACCOUNT_TYPES = ('expense', 'expense_direct_cost',
                               'expense_depreciation')


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

    # ── CR3-FINAL round 3, item 10 ────────────────────────────────────────
    def resolve_expense_account(self, company=None, raise_if_missing=False):
        """The GL account this category posts to, or an empty recordset.

        Order: the per-company map in Payroll & Accounting Setup, then the
        category's own default. A candidate is only accepted if it is a P&L
        cost account — a mapped-but-wrong account (asset, cash, receivable)
        is treated as no account at all, because posting a project cost to a
        balance-sheet account corrupts the P&L silently.
        """
        self.ensure_one()
        Account = self.env['account.account']
        company = company or self.env.company
        settings = self.env['way4tech.payroll.settings'].get_for_company(company.id)
        candidates = settings.manpower_expense_category_account_ids.filtered(
            lambda m: m.category_id == self
        )[:1].mapped('account_id')
        if self.default_expense_account_id:
            candidates |= self.default_expense_account_id
        account = candidates.filtered(
            lambda a: a.account_type in VALID_EXPENSE_ACCOUNT_TYPES
        )[:1]
        if account:
            return account
        if raise_if_missing:
            wrong = candidates - account
            if wrong:
                raise UserError(_(
                    'Category "%(cat)s" is mapped to account %(code)s '
                    '%(name)s, which is a %(type)s account — not a cost '
                    'account. Posting a project cost there would corrupt the '
                    'P&L.\n\nFix the mapping in Configuration → Payroll & '
                    'Accounting Setup → Manpower Contracts → Expense Category '
                    'map.'
                ) % {'cat': self.display_name, 'code': wrong[:1].code or '',
                     'name': wrong[:1].name or '',
                     'type': wrong[:1].account_type or ''})
            raise UserError(_(
                'No expense account configured for category "%(cat)s".\n\n'
                'Set it in Configuration → Payroll & Accounting Setup → '
                'Manpower Contracts → Expense Category map before using this '
                'category.'
            ) % {'cat': self.display_name})
        return Account.browse()

    @api.model
    def unmapped_categories(self, company=None):
        """Categories with no usable cost account — surfaced in settings."""
        company = company or self.env.company
        return self.search([]).filtered(
            lambda c: not c.resolve_expense_account(company)
        )
