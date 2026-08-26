# -*- coding: utf-8 -*-
"""Project Budget line (P7) — Budget vs Actual per expense category on a
Manpower Contract.

``actual_amount`` sums real posted journal items on expense accounts tagged
with the contract's analytic account (contract.analytic_distribution +
contract.analytic_account_id) filtered to lines whose account_id matches
this budget line's expense_account_id.
"""
from odoo import _, api, fields, models


class Way4TechManpowerContractBudgetLine(models.Model):
    _name = "way4tech.manpower.contract.budget.line"
    _description = "Manpower Contract — Project Budget Line"
    _inherit = ['way4tech.manpower.approval.mixin']
    # See income-line comment: date in _order causes row resort on every
    # date pick in editable inline lists → picker reopen loop. id desc only.
    _order = "id desc"

    contract_id = fields.Many2one(
        "way4tech.manpower.contract", required=True, ondelete="cascade",
    )
    company_id = fields.Many2one(related="contract_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="contract_id.currency_id", store=True, readonly=True)

    category_id = fields.Many2one(
        "way4tech.expense.category", string="Expense Type", required=True,
    )
    description = fields.Char(string="Description")
    expense_account_id = fields.Many2one(
        "account.account", string="Expense Account", check_company=True,
    )
    budget_amount = fields.Monetary(string="Budget Amount", currency_field="currency_id")
    # CR3-FINAL round 5: STORED, and now derived from the contract's Project
    # Expense lines (see _compute_actual_amount). Its @api.depends reach those
    # lines, so posting/cancelling a bill flows here through the ORM — the old
    # raw-SQL + manual-trigger design is gone. Stored so Total Actual Cost and
    # everything derived from it stay usable as pivot measures.
    actual_amount = fields.Monetary(
        string="Actual Amount",
        compute="_compute_actual_amount",
        store=True,
        currency_field="currency_id",
    )
    remaining = fields.Monetary(
        string="Remaining",
        compute="_compute_remaining",
        currency_field="currency_id",
    )
    status = fields.Char(
        string="Status",
        compute="_compute_status",
        help="✅ On Budget when Remaining ≥ 0, ⛔ Over when < 0.",
    )
    # CR2 G5 (19.0.2.9.0): draft/confirmed gate. Only 'confirmed' budget
    # lines contribute to bs_total_budget_cost / bs_total_actual_cost;
    # 'draft' lines are proposals awaiting sign-off.
    state = fields.Selection(
        selection=[('draft', 'Draft'), ('confirmed', 'Confirmed')],
        string='Approval State', default='draft', copy=False,
        help='Draft budget lines do NOT count toward Total Budget / Total '
             'Actual on the Billing Summary. Use action_confirm to promote.',
    )
    state_display = fields.Char(
        string='State (Display)', compute='_compute_state_display',
        help='CR2 G5 skeptic amendment 5: readable label for QWeb PDF '
             '(avoids reaching into _fields.selection from templates).',
    )
    # store=False to avoid the row-rerender loop when the user picks Date
    # in the inline list. See the same fix on income line.inv_month.
    month = fields.Char(string="Month", compute="_compute_month")
    # CR4 item 3: default from the contract's Start Date month, not today.
    date = fields.Date(
        string="Date",
        default=lambda self: self._way4tech_default_period_date())

    # ── Compute methods ─────────────────────────────────────────────────────

    @api.onchange("category_id")
    def _onchange_category_default_account(self):
        """CR3-FINAL round 3, item 10: fill from configuration on every category
        change, through the guarded resolver.

        Previously this only filled a BLANK cell and fell back to the category's
        own default without checking the account type — which is how a Building
        Maintenance budget line ended up on 120006 InterCompany Petty cash, an
        asset account. Now a category with no usable COST account fills nothing,
        and action_confirm refuses by name.
        """
        if not self.category_id:
            self.expense_account_id = False
            return
        company = self.contract_id.company_id or self.env.company
        self.expense_account_id = self.category_id.resolve_expense_account(company)
        # CR3-FINAL round 4, item 7: surface the gap immediately.
        if not self.expense_account_id:
            return {'warning': {
                'title': _('No expense account configured'),
                'message': _(
                    'Category "%s" has no expense account mapped. Set it in '
                    'Configuration → Payroll & Accounting Setup → Manpower '
                    'Contracts → Expense Category map, or pick an account on '
                    'this line. The budget line cannot be confirmed until it '
                    'has one.'
                ) % self.category_id.display_name,
            }}

    def _get_analytic_account_ids(self):
        """Union of analytic accounts used by the parent contract (both the
        multi-account Json and the legacy single-account field)."""
        self.ensure_one()
        ids = set()
        if self.contract_id.analytic_distribution:
            for key in self.contract_id.analytic_distribution:
                # keys can be "id" or "id,id" for cross-plan distributions
                for part in str(key).split(","):
                    try:
                        ids.add(int(part))
                    except (TypeError, ValueError):
                        continue
        if self.contract_id.analytic_account_id:
            ids.add(self.contract_id.analytic_account_id.id)
        return list(ids)

    @api.depends(
        'category_id', 'date',
        'contract_id.project_expense_ids.amount',
        'contract_id.project_expense_ids.state',
        'contract_id.project_expense_ids.category_id',
        'contract_id.project_expense_ids.date',
        'contract_id.project_expense_ids.bill_id.date',
    )
    def _compute_actual_amount(self):
        """CR3-FINAL round 5, issues 1+2 — Actual = billed spend for THIS
        budget line's CATEGORY in its MONTH, read from the contract's own
        Project Expense lines.

        The previous design scanned posted journal-items by
        account + analytic + month. It was dead on real data: spend lands on
        the account with NO analytic (e.g. bank payments), so the analytic
        match returned 0 while the dashboard's Operating Expenses (which reads
        the expense LINES directly) showed the real number. The two disagreed
        because they measured different things.

        This reads the SAME source as bs_total_project_cgs / bs_total_project_exp
        — the contract's billed Project Expense lines — filtered to this
        budget line's category and month. Consequences:
          * Actual now equals the dashboard for that category, by construction.
          * It recomputes automatically the moment an expense line is billed
            (the @api.depends on project_expense_ids.state), and drops back if
            a bill is reset/cancelled — NO manual trigger, NO analytic needed.
          * Because it is driven by the EXPENSE lines, not by a write to this
            budget line, Actual keeps moving even after the budget line is
            approved (issue 2) — approval froze the plan (Budget Amount), the
            Actual is a live figure the approver never signed off.
        """
        for line in self:
            if not line.category_id or not line.date:
                line.actual_amount = 0.0
                continue
            d = line.date
            month_start = d.replace(day=1)
            if d.month == 12:
                next_month = d.replace(year=d.year + 1, month=1, day=1)
            else:
                next_month = d.replace(month=d.month + 1, day=1)

            def _eff_date(e):
                # Alzain Fix 1 (2026-08): the month a billed cost belongs to is
                # the month its POSTED bill actually posts to the P&L — i.e. the
                # bill's accounting date — not the expense LINE's own `date`
                # field, which can diverge from it (e.g. an Operating-Exp bill
                # block whose Accounting Date is Jul 1 while the line's date is
                # left at another month). Matching on the line's date left that
                # cost out of the July budget (Actual stayed 0). Prefer the
                # posted bill's date; fall back to the line date when there is
                # no posted bill.
                if e.bill_id and e.bill_id.date:
                    return e.bill_id.date
                return e.date

            line.actual_amount = sum(
                e.amount or 0.0
                for e in line.contract_id.project_expense_ids
                if e.category_id == line.category_id
                and e.state == 'billed'
                and _eff_date(e) and month_start <= _eff_date(e) < next_month
            )

    @api.depends("budget_amount", "actual_amount")
    def _compute_remaining(self):
        for line in self:
            line.remaining = (line.budget_amount or 0.0) - (line.actual_amount or 0.0)

    @api.depends("remaining")
    def _compute_status(self):
        for line in self:
            if (line.remaining or 0.0) >= 0.0:
                line.status = "✅ On Budget"
            else:
                line.status = "⛔ Over"

    @api.depends("date")
    def _compute_month(self):
        for line in self:
            line.month = line.date.strftime("%m/%Y") if line.date else False

    @api.depends('state')
    def _compute_state_display(self):
        labels = dict(self._fields['state'].selection)
        for line in self:
            line.state_display = labels.get(line.state, line.state or '')

    # CR2 G5 (19.0.2.9.0): approval transitions.
    def action_confirm(self):
        """draft → confirmed. Line now contributes to KPI totals.

        CR3-FINAL Part A point 2: Confirm is one of the six gated actions —
        it changes the reported figures, so it needs its own approval, and
        that approval is consumed here.
        """
        for line in self:
            if line.state != 'confirmed':
                # CR3-FINAL round 3, item 10: a confirmed budget line feeds
                # Actual Cost, which is read from journal items on this
                # account. Confirming one pointed at the wrong account (or no
                # account) would quietly skew the whole budget comparison.
                if not line.expense_account_id and line.category_id:
                    line.expense_account_id = \
                        line.category_id.resolve_expense_account(
                            line.contract_id.company_id or self.env.company,
                            raise_if_missing=True,
                        )
                line.contract_id._require_month_approval(record=line)
                line.state = 'confirmed'
                line.contract_id._consume_approval(line)
        return True

    def action_reset_draft(self):
        """confirmed → draft. Line drops out of KPI totals."""
        for line in self:
            line.state = 'draft'
        return True
