# -*- coding: utf-8 -*-
"""Project Budget line (P7) — Budget vs Actual per expense category on a
Manpower Contract.

``actual_amount`` sums real posted journal items on expense accounts tagged
with the contract's analytic account (contract.analytic_distribution +
contract.analytic_account_id) filtered to lines whose account_id matches
this budget line's expense_account_id.
"""
from odoo import api, fields, models


class Way4TechManpowerContractBudgetLine(models.Model):
    _name = "way4tech.manpower.contract.budget.line"
    _description = "Manpower Contract — Project Budget Line"
    _order = "date desc, id desc"

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
    actual_amount = fields.Monetary(
        string="Actual Amount",
        compute="_compute_actual_amount",
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
    date = fields.Date(string="Date", default=fields.Date.context_today)

    # ── Compute methods ─────────────────────────────────────────────────────

    @api.onchange("category_id")
    def _onchange_category_default_account(self):
        if not self.expense_account_id and self.category_id and self.contract_id:
            settings = self.env["way4tech.payroll.settings"].get_for_company(
                self.contract_id.company_id.id,
            )
            mapping = settings.manpower_expense_category_account_ids.filtered(
                lambda m: m.category_id == self.category_id
            )[:1]
            if mapping:
                self.expense_account_id = mapping.account_id
            elif self.category_id.default_expense_account_id:
                self.expense_account_id = self.category_id.default_expense_account_id

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

    def _compute_actual_amount(self):
        for line in self:
            actual = 0.0
            analytic_ids = line._get_analytic_account_ids()
            if line.expense_account_id and analytic_ids:
                # Match any journal-item whose analytic_distribution JSON
                # contains a key referring to one of the contract's analytics.
                # Use SQL for correctness with JSONB.
                self.env.cr.execute(
                    """
                    SELECT COALESCE(SUM(aml.debit - aml.credit), 0)
                    FROM account_move_line aml
                    JOIN account_move am ON am.id = aml.move_id
                    WHERE aml.account_id = %s
                      AND am.state = 'posted'
                      AND EXISTS (
                          SELECT 1
                          FROM jsonb_object_keys(COALESCE(aml.analytic_distribution, '{}'::jsonb)) AS k
                          WHERE EXISTS (
                              SELECT 1
                              FROM unnest(string_to_array(k, ',')) AS part
                              WHERE part::int = ANY(%s)
                          )
                      )
                    """,
                    (line.expense_account_id.id, analytic_ids),
                )
                result = self.env.cr.fetchone()
                if result:
                    actual = float(result[0] or 0.0)
            line.actual_amount = actual

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
        """draft → confirmed. Line now contributes to KPI totals."""
        for line in self:
            if line.state != 'confirmed':
                line.state = 'confirmed'
        return True

    def action_reset_draft(self):
        """confirmed → draft. Line drops out of KPI totals."""
        for line in self:
            line.state = 'draft'
        return True
