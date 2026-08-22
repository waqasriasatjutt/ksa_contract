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

# Part 1 (2026-08): Other Payable tab. A category whose mapped account is one of
# these liability types CANNOT be billed (bills only post to expense accounts) —
# it is automatically routed to the Other Payable (Journal Entry) tab instead.
# Detection reuses the SAME Expense Category → Account map; no new config.
VALID_PAYABLE_ACCOUNT_TYPES = ('liability_payable', 'liability_current',
                               'liability_non_current')


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

    # ── CR9 hardening (2026-07-30) ────────────────────────────────────────
    def _acct_ok_for_company(self, account, company):
        """True if `account` may be used by `company` — i.e. it is either a
        shared account (no company_ids) or scoped to `company`.

        Read via ``sudo()`` on purpose: a cross-company account is precisely
        the one the multi-company record rule would block, so a plain read of
        its ``company_ids`` here would itself raise the Access Error we are
        trying to prevent. Sudo only reads the scoping columns; it never posts
        or resolves anything.
        """
        if not account:
            return False
        acct = account.sudo()
        # Odoo 17+: account.account is multi-company via company_ids (empty =
        # shared across all companies). Keep a single-company fallback in case
        # a future/base variant exposes company_id instead.
        if 'company_ids' in acct._fields:
            return (not acct.company_ids) or (company in acct.company_ids)
        if 'company_id' in acct._fields:
            return (not acct.company_id) or (acct.company_id == company)
        return True

    # ── CR3-FINAL round 3, item 10 ────────────────────────────────────────
    def resolve_expense_account(self, company=None, raise_if_missing=False):
        """The GL account this category posts to, or an empty recordset.

        Order: the per-company map in Payroll & Accounting Setup, then the
        category's own default. A candidate is only accepted if it is (1) a P&L
        cost account and (2) usable by `company`. A mapped-but-wrong account
        (asset, cash, receivable) is treated as no account at all, because
        posting a project cost to a balance-sheet account corrupts the P&L
        silently.

        CR9 hardening: the category's ``default_expense_account_id`` is a single
        SHARED field pointing at exactly one company's account. Previously it
        was appended unconditionally, so resolving for any OTHER company handed
        back that company's account and the caller then hit a multi-company
        Access Error on save. Now the default (and every candidate) is only
        accepted when it belongs to — or is shared with — the requesting
        company. When nothing company-valid is found the resolver returns
        empty and the callers show a clear "configure an account for this
        company" message, instead of silently reaching across companies.
        """
        self.ensure_one()
        Account = self.env['account.account']
        company = company or self.env.company
        settings = self.env['way4tech.payroll.settings'].get_for_company(company.id)
        # The per-company map is already company-scoped (settings is per company
        # and the map's account carries check_company), so its account is safe.
        candidates = settings.manpower_expense_category_account_ids.filtered(
            lambda m: m.category_id == self
        )[:1].mapped('account_id')
        # Only fall back to the shared category default when it is valid for
        # THIS company — never leak another company's account across.
        if self.default_expense_account_id and self._acct_ok_for_company(
                self.default_expense_account_id, company):
            candidates |= self.default_expense_account_id
        account = candidates.filtered(
            lambda a: a.account_type in VALID_EXPENSE_ACCOUNT_TYPES
            and self._acct_ok_for_company(a, company)
        )[:1]
        if account:
            return account
        if raise_if_missing:
            wrong = candidates.filtered(
                lambda a: self._acct_ok_for_company(a, company)
            ) - account
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
                'No expense account configured for category "%(cat)s" in '
                'company "%(company)s".\n\nSet it in Configuration → Payroll & '
                'Accounting Setup → Manpower Contracts → Expense Category map '
                '(for this company) before using this category.'
            ) % {'cat': self.display_name, 'company': company.display_name})
        return Account.browse()

    @api.model
    def unmapped_categories(self, company=None):
        """Categories with no usable cost account — surfaced in settings."""
        company = company or self.env.company
        return self.search([]).filtered(
            lambda c: not c.resolve_expense_account(company)
        )

    # ── Part 1 (2026-08): Other Payable routing (reuses the existing map) ──
    def _mapped_account_for_company(self, company):
        """The RAW mapped GL account for this category + company (per-company
        map first, then the category default) WITHOUT the P&L-cost-type filter.
        Used only to detect the account's type for routing — never to post."""
        self.ensure_one()
        settings = self.env['way4tech.payroll.settings'].get_for_company(company.id)
        acc = settings.manpower_expense_category_account_ids.filtered(
            lambda m: m.category_id == self
        )[:1].mapped('account_id')
        if not acc and self.default_expense_account_id and \
                self._acct_ok_for_company(self.default_expense_account_id, company):
            acc = self.default_expense_account_id
        return acc[:1]

    def way4tech_is_payable_category(self, company=None):
        """True when this category's mapped account is a Payable/Liability type
        — the confirmed marker that its entries must be routed to the Other
        Payable (Journal Entry) tab instead of Direct Cost / Operating Exp.
        Automatic + config-free: it reads the SAME Expense Category → Account
        map the client already maintains."""
        self.ensure_one()
        company = company or self.env.company
        acc = self._mapped_account_for_company(company)
        return bool(acc) and acc.account_type in VALID_PAYABLE_ACCOUNT_TYPES

    def resolve_payable_account(self, company=None, raise_if_missing=False):
        """The mapped Payable/Liability GL account for the Other Payable Journal
        Entry, or empty. Mirror of resolve_expense_account for liability types."""
        self.ensure_one()
        company = company or self.env.company
        acc = self._mapped_account_for_company(company)
        if acc and acc.account_type in VALID_PAYABLE_ACCOUNT_TYPES and \
                self._acct_ok_for_company(acc, company):
            return acc
        if raise_if_missing:
            raise UserError(_(
                'Category "%(cat)s" has no Payable/Liability account mapped for '
                'company "%(company)s".\n\nMap it in Configuration → Payroll & '
                'Accounting Setup → Manpower Contracts → Expense Category map.'
            ) % {'cat': self.display_name, 'company': company.display_name})
        return self.env['account.account'].browse()
