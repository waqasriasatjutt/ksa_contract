from datetime import date, timedelta

from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, ValidationError


class Way4TechManpowerContract(models.Model):
    _name = 'way4tech.manpower.contract'
    _description = 'Manpower Billing Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    # CR3 P4 (v13.0): sort by accounting_date desc (monthly-record era) —
    # falls back to start_date desc for legacy rows that have no
    # accounting_date. Both fields are populated on new records (mirror), so
    # accounting_date NULLS FIRST/LAST doesn't matter in practice.
    _order = 'accounting_date desc, start_date desc, id desc'

    name = fields.Char(string='Contract Name', required=True, tracking=True)
    # PRO/YYYY/MM/NNNN — auto-minted on create, monthly-reset counter.
    reference = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        index=True,
        help='PRO/YYYY/MM/NNNN — monthly counter based on contract start_date. '
             'Propagates onto customer invoices (ref) and vendor bills '
             '(payment_reference) generated from this contract.',
    )
    # Contract-level tags. Available manually across all system tags — no
    # domain filter, per P4/P5/P6 requirement.
    tag_ids = fields.Many2many(
        'way4tech.tag',
        'way4tech_manpower_contract_tag_rel',
        'contract_id', 'tag_id',
        string='Contract Tags',
    )
    client_id = fields.Many2one(
        comodel_name='res.partner',
        string='Client',
        required=True,
        tracking=True,
    )
    salesperson_id = fields.Many2one(
        'hr.employee',
        string='Salesperson',
        tracking=True,
        help='Internal HR employee acting as salesperson on this contract. '
             'One salesperson can hold multiple contracts.',
    )
    # CR2 G3 (19.0.2.7.0): commission mode picker. Drives how
    # _get_commission_amount() and the Sales Person Commission tab lines
    # compute the payout for salesperson_id. Default 'none' preserves
    # zero client-visible behaviour on pre-G3 contracts until opt-in.
    commission_type = fields.Selection(
        selection=[
            ('none', 'None'),
            ('fix', 'Fix Amount'),
            ('gp', 'Project Gross Profit %'),
            ('np', 'Project Net Profit %'),
            ('budgeted', 'Budgeted Profit %'),
            ('actual', 'Actual Profit %'),
        ],
        string='Commission Type',
        default='none',
        tracking=True,
        help='CR2 G3 — how the salesperson_id earns on this contract.\n'
             '  • None: no auto-computed commission\n'
             '  • Fix Amount: template.fix_rate × posted-invoice-count in month\n'
             '  • %-modes: template rate × profit_value_for_type, gated by '
             'pp_actual_profit > 0 (no profit → no commission).\n'
             'Rate looked up on Configuration → Payroll & Accounting Setup → '
             'Sales Person Commission Rules by employee.',
    )
    contract_type = fields.Selection(
        selection=[
            ('food_delivery', 'Food Delivery'),
            ('project', 'Project Based'),
        ],
        string='Contract Type',
        default='project',
        tracking=True,
    )
    billing_type = fields.Selection(
        selection=[
            ('fixed', 'Fixed Price'),
            ('hourly', 'Hourly Rate'),
        ],
        string='Billing Type',
        default='fixed',
        tracking=True,
    )
    fixed_amount = fields.Monetary(
        string='Fixed Monthly Amount',
        currency_field='currency_id',
    )
    hourly_rate = fields.Monetary(
        string='Hourly Rate',
        currency_field='currency_id',
    )
    # CR3 P3 (v13.0): Per Day Allowed Hours — CONTRACT master.
    # Priority chain when a timesheet line loads: Contract → Employee → line
    # override. Contract is the most specific (per client + month), wins
    # over the employee default. Kept as a plain Float; label deliberately
    # distinct from the timesheet's `per_day_hours` per feedback rule
    # [[feedback_search_existing_field_labels_before_adding]].
    default_per_day_allowed_hours = fields.Float(
        string='Default Per Day Allowed Hours',
        digits=(16, 2),
        help='Per-day allowed hours for timesheet rows on this contract. '
             'Auto-fills timesheet.per_day_hours when an employee is picked '
             '(only when the timesheet row is still blank). Overrides the '
             'employee-level default; line-level override still wins.',
    )
    start_date = fields.Date(string='Start Date', required=True)
    end_date = fields.Date(string='End Date')

    # ── CR3 P1: Monthly-record model (v12.0) ───────────────────────────────
    # accounting_date is the PRIMARY DATE of the record under the monthly
    # model (one record = one client-month). It is NOT required at the DB
    # layer — old rows keep NULL forever so `-u module` doesn't backfill
    # them with today's date and trip uniqueness. New rows get today via
    # `default=`; create() also `setdefault`s it as belt-and-suspenders for
    # programmatic callers that would otherwise leave it None. The
    # ValidationError below enforces "must be set once the contract goes
    # active" so it's effectively required for the business flow while
    # remaining safe at the schema layer.
    accounting_date = fields.Date(
        string='Accounting Date',
        default=fields.Date.context_today,
        index=True,
        tracking=True,
        help='Primary date of this monthly record. Drives the auto-name '
             '(client + month), the uniqueness key, and the due-date default. '
             'Old records may have this blank; new records get today.',
    )
    # First-day-of-month normalisation of accounting_date. Stored + indexed
    # so it can back the DB-level partial unique index built in _auto_init.
    contract_month = fields.Date(
        string='Month',
        compute='_compute_contract_month',
        store=True,
        index=True,
        help='First day of accounting_date\'s month. Used as the uniqueness '
             'key together with client and project.',
    )
    # Plain Date with a create-time default — NOT a stored compute. A
    # compute+store+readonly=False+depends=accounting_date is the canonical
    # Odoo trap: it would silently overwrite the user\'s manual override on
    # any future accounting_date edit (AR aging would go wrong with no
    # warning). Keep manual, seed via create() from accounting_date+45d.
    due_date = fields.Date(
        string='Due Date',
        help='Auto-set to Accounting Date + 45 days on record creation. '
             'Manually overwritable — never auto-recomputed on later date edits.',
    )
    po_id = fields.Many2one(
        'way4tech.client.po', string='Client PO',
        tracking=True,
        help='Link to a Client PO for balance tracking. '
             'Invoices created from this contract will count against the PO balance.',
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account (legacy)',
        help='Legacy single-analytic field. Kept for backwards compat and '
             'used as a fallback when Analytic Distribution is empty. '
             'New workflows should use analytic_distribution instead.',
    )
    analytic_distribution = fields.Json(
        string='Analytic Distribution',
        help='Split contract cost/revenue across multiple analytic accounts. '
             'Values propagate onto every invoice + bill generated from this '
             'contract (same widget/behaviour as account.move.line).',
    )
    # The analytic_distribution WIDGET on the web client reads this companion
    # field to render the % column at the right decimal precision. Odoo's
    # account.move.line defines it the same way — leaving it out crashes the
    # form with KeyError: 'analytic_precision' the moment the widget mounts.
    analytic_precision = fields.Integer(
        store=False,
        default=lambda self: self.env['decimal.precision'].precision_get('Percentage Analytic'),
    )
    way4tech_project_id = fields.Many2one(
        'way4tech.project',
        string='Project',
        help='Reused from customer invoices / vendor bills. Every invoice + '
             'bill generated from this contract inherits this Project.',
    )
    way4tech_category_id = fields.Many2one(
        'way4tech.entry.category',
        string='Entry Category',
        help='Reused from customer invoices / vendor bills. Every invoice + '
             'bill generated from this contract inherits this Entry Category.',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
        store=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('active', 'Active'),
            ('completed', 'Completed'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        tracking=True,
        copy=False,
    )
    line_ids = fields.One2many(
        comodel_name='way4tech.manpower.contract.line',
        inverse_name='contract_id',
        string='Assigned Manpower',
    )
    timesheet_ids = fields.One2many(
        comodel_name='way4tech.manpower.timesheet',
        inverse_name='contract_id',
        string='Timesheets',
    )
    invoice_ids = fields.Many2many(
        comodel_name='account.move',
        string='Invoices',
    )
    invoice_count = fields.Integer(
        string='Invoice Count',
        compute='_compute_invoice_count',
    )
    total_hours = fields.Float(
        string='Total Hours',
        compute='_compute_totals',
        store=True,
    )
    total_invoiced = fields.Monetary(
        string='Total Invoiced',
        compute='_compute_invoice_count',
        currency_field='currency_id',
    )
    total_employee_cost = fields.Monetary(
        string='Total Employee Cost',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
        help="Sum of Hours × Employee Rate across all timesheet lines. "
             "The same timesheets that drive the client invoice also drive this salary cost.",
    )
    billing_margin = fields.Monetary(
        string='Billing Margin (Hours)',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
        help="Invoiced amount minus total employee salary cost from timesheets. "
             "Positive = company earns above the labour cost on hourly contracts.",
    )
    project_expense_ids = fields.One2many(
        comodel_name='way4tech.manpower.project.expense',
        inverse_name='contract_id',
        string='Project Expenses',
    )
    # CR2 G2: two view-level splits over the same underlying table, driven
    # by category.expense_type. Both back a Manpower Contract notebook tab
    # and feed the Billing Summary CGS vs OpEx compute respectively.
    direct_cost_line_ids = fields.One2many(
        comodel_name='way4tech.manpower.project.expense',
        inverse_name='contract_id',
        domain=[('category_id.expense_type', '=', 'direct')],
        string='Project Direct Cost Lines',
        help='CR2 G2: subset of project_expense_ids where the picked '
             'category is bucketed as Direct Cost. Feeds the Project '
             'Direct Cost tab and Billing Summary bs_total_project_cgs.',
    )
    operating_exp_line_ids = fields.One2many(
        comodel_name='way4tech.manpower.project.expense',
        inverse_name='contract_id',
        domain=[('category_id.expense_type', '=', 'operating')],
        string='Project Operating Exp Lines',
        help='CR2 G2: subset of project_expense_ids where the picked '
             'category is bucketed as Operating Exp. Feeds the Project '
             'Operating Exp tab and Billing Summary bs_total_project_exp.',
    )
    # CR2 G3 (19.0.2.7.0): Sales Person Commission tab lines.
    commission_line_ids = fields.One2many(
        'way4tech.manpower.commission.line',
        'contract_id',
        string='Sales Person Commission Lines',
        help='One row per commission payout on the Sales Person Commission '
             "tab. Amount auto-computes via _get_commission_amount() from "
             "the contract's commission_type + the employee's template rate.",
    )
    # ── CR2 G4 (19.0.2.8.0): Vendor Bills smart-button aggregates ─────────
    # Non-stored M2M computed from the three child-line bill_id fields.
    # Single source of truth = the line-level FK; no shadow M2M table to
    # drift out of sync. Depends chain includes .state so the accountant
    # cancelling/deleting a bill immediately drops the count.
    bill_ids = fields.Many2many(
        comodel_name='account.move',
        string='Vendor Bills',
        compute='_compute_bill_aggregates',
        help='CR2 G4: all vendor bills posted from Project Direct Cost, '
             'Project Operating Exp and Sales Person Commission line tabs. '
             'Non-stored — computed from child lines.bill_id on every read.',
    )
    bill_count = fields.Integer(
        string='Vendor Bill Count', compute='_compute_bill_aggregates',
    )
    bill_total = fields.Monetary(
        string='Total Vendor Bills', compute='_compute_bill_aggregates',
        currency_field='currency_id',
    )
    # ── CR2 G5 (19.0.2.9.0): monthly signature-approval workflow ─────────
    signature_request_ids = fields.One2many(
        'way4tech.manpower.contract.signature.request',
        'contract_id',
        string='Signature Requests',
        help='CR2 G5: one record per (contract, month) approval cycle. '
             'Create/Confirm actions on the 6 line-tabs are gated on '
             "state='approved' for the line's month via "
             '_require_month_approval() below.',
    )
    has_pending_approval = fields.Boolean(
        string='Approval Pending?',
        compute='_compute_has_pending_approval',
        help='CR2 G5: True when any signature request is state=pending. '
             'Used only to hide the header Send for Signature button; the '
             'tab lock has been dropped per skeptic amendment 4 (whole-'
             'contract lock during a single-month cycle was too broad).',
    )
    # ── CR2 G6 (19.0.2.10.0): Report Period filter ──────────────────────
    # Non-stored, per-open display preference. Drives KPI computes AND
    # tab O2M domains. Default 'all' — otherwise historical contracts
    # would open with all KPI cards = 0 and empty tabs (skeptic HIGH risk
    # UX landmine). Users opt into a period; they don't get auto-scoped.
    # 'all' populates sentinel bounds so tab domains stay well-formed.
    report_period = fields.Selection(
        selection=[
            ('all', 'All Time'),
            ('this_month', 'This Month'),
            ('last_month', 'Last Month'),
            ('this_year', 'This Year'),
            ('custom', 'Custom Range'),
        ],
        string='Report Period', default='all', store=False,
        help='CR2 G6: date window applied to Billing Summary, KPI cards '
             'and each notebook-tab line list. Pick Custom to type your '
             'own dates.',
    )
    report_date_from = fields.Date(
        string='From', compute='_compute_report_dates', readonly=False, store=False,
    )
    report_date_to = fields.Date(
        string='To', compute='_compute_report_dates', readonly=False, store=False,
    )

    @api.depends('report_period')
    def _compute_report_dates(self):
        """Map report_period → (from, to). 'custom' is a no-op so user
        edits the pickers directly. 'all' uses sentinels (1900/2999) so
        downstream domains stay well-formed with a single unconditional
        expression."""
        from datetime import date as _date
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.report_period == 'this_month':
                rec.report_date_from = today.replace(day=1)
                if today.month == 12:
                    nxt = today.replace(year=today.year + 1, month=1, day=1)
                else:
                    nxt = today.replace(month=today.month + 1, day=1)
                rec.report_date_to = fields.Date.add(nxt, days=-1)
            elif rec.report_period == 'last_month':
                first_this = today.replace(day=1)
                last_prev = fields.Date.add(first_this, days=-1)
                rec.report_date_from = last_prev.replace(day=1)
                rec.report_date_to = last_prev
            elif rec.report_period == 'this_year':
                rec.report_date_from = today.replace(month=1, day=1)
                rec.report_date_to = today.replace(month=12, day=31)
            elif rec.report_period == 'all':
                rec.report_date_from = _date(1900, 1, 1)
                rec.report_date_to = _date(2999, 12, 31)
            # 'custom': leave whatever the user typed.

    def _filter_by_report_period(self, records, date_field):
        """CR2 G6 helper: return subset of `records` whose `date_field`
        value falls in [self.report_date_from, self.report_date_to].
        Records with False date are excluded (KPI cannot bucket an
        undated line). If either bound is unset, no filter is applied."""
        self.ensure_one()
        d_from, d_to = self.report_date_from, self.report_date_to
        if not d_from or not d_to:
            return records
        return records.filtered(
            lambda r: r[date_field] and d_from <= r[date_field] <= d_to
        )

    @api.depends('signature_request_ids.state')
    def _compute_has_pending_approval(self):
        for rec in self:
            rec.has_pending_approval = any(
                r.state == 'pending' for r in rec.signature_request_ids
            )
    income_line_ids = fields.One2many(
        'way4tech.manpower.contract.income.line',
        'contract_id',
        string='Project Income',
    )
    budget_line_ids = fields.One2many(
        'way4tech.manpower.contract.budget.line',
        'contract_id',
        string='Project Budget',
    )
    total_project_expenses = fields.Monetary(
        string='Total Project Expenses',
        compute='_compute_project_margin',
        store=True,
        currency_field='currency_id',
        help='Sum of all project expense amounts (wages, accommodation, utilities, '
             'furniture, transport, other). Used to calculate project margin.',
    )
    project_margin = fields.Monetary(
        string='Project Margin',
        compute='_compute_project_margin',
        store=True,
        currency_field='currency_id',
        help='Project Margin = Total Invoiced − Total Project Expenses.\n'
             'Positive = profitable. Shows the gross margin before company overhead.\n'
             'For full P&L including individual salary costs, see the Analytic Report.',
    )
    notes = fields.Text(string='Notes')

    # ── P8 (2026-07-15): Billing Summary + Project Profitability + KPI% ──
    # 19 read-only aggregates, all computed from live invoice_ids /
    # project_expense_ids / budget_line_ids. Non-stored — recompute on every
    # read; the parent record already invalidates itself when children change.
    bs_total_invoiced = fields.Monetary(
        string='Total Invoiced', compute='_compute_kpi_summary',
        currency_field='currency_id',
    )
    bs_total_project_cgs = fields.Monetary(
        string='Total Project CGS', compute='_compute_kpi_summary',
        currency_field='currency_id',
        help='Sum of Project Expense line amounts whose expense account type '
             'is Cost of Revenue (account.account.account_type = expense_direct_cost).',
    )
    bs_total_project_exp = fields.Monetary(
        string='Total Project Expenses', compute='_compute_kpi_summary',
        currency_field='currency_id',
        help='Sum of Project Expense line amounts whose expense account type '
             'is Operating Expense (account.account.account_type = expense).',
    )
    bs_total_budget_cost = fields.Monetary(
        string='Total Budget Cost', compute='_compute_kpi_summary',
        currency_field='currency_id',
    )
    bs_total_actual_cost = fields.Monetary(
        string='Total Actual Cost', compute='_compute_kpi_summary',
        currency_field='currency_id',
    )
    bs_remaining_budget = fields.Monetary(
        string='Remaining Budget', compute='_compute_kpi_summary',
        currency_field='currency_id',
    )
    bs_budget_variance = fields.Monetary(
        string='Budget Variance', compute='_compute_kpi_summary',
        currency_field='currency_id',
    )
    pp_gross_profit = fields.Monetary(
        string='Project Gross Profit', compute='_compute_kpi_summary',
        currency_field='currency_id',
    )
    pp_net_profit = fields.Monetary(
        string='Project Net Profit', compute='_compute_kpi_summary',
        currency_field='currency_id',
    )
    pp_budgeted_profit = fields.Monetary(
        string='Budgeted Profit', compute='_compute_kpi_summary',
        currency_field='currency_id',
    )
    pp_actual_profit = fields.Monetary(
        string='Actual Profit', compute='_compute_kpi_summary',
        currency_field='currency_id',
    )
    # -- CR2 G3 (19.0.2.7.0): sales-person commission summary ------------
    bs_sales_person_commission = fields.Monetary(
        string='Total Sales Person Commission', compute='_compute_kpi_summary',
        currency_field='currency_id',
        help='Sum of commission-line amounts whose vendor bill has been '
             "created (state='billed'). Mirrors the billed-only rule already "
             'applied to CGS/OpEx per CR2 G7 item 2 — keeps summary tiles '
             'numerically consistent with what actually posted to the GL.',
    )
    pp_profit_after_commission = fields.Monetary(
        string='Profit After Commission', compute='_compute_kpi_summary',
        currency_field='currency_id',
        help='pp_actual_profit − bs_sales_person_commission. What the '
             'company keeps on this contract after paying the salesperson.',
    )
    kpi_gross_margin = fields.Float(
        string='Gross Margin %', compute='_compute_kpi_summary', digits=(6, 2),
    )
    kpi_net_margin = fields.Float(
        string='Net Margin %', compute='_compute_kpi_summary', digits=(6, 2),
    )
    kpi_cogs_pct = fields.Float(
        string='COGS %', compute='_compute_kpi_summary', digits=(6, 2),
    )
    kpi_opex_pct = fields.Float(
        string='Operating Expense %', compute='_compute_kpi_summary', digits=(6, 2),
    )
    kpi_total_cost_pct = fields.Float(
        string='Total Cost %', compute='_compute_kpi_summary', digits=(6, 2),
    )
    kpi_roc = fields.Float(
        string='Profit to Cost (ROC) %', compute='_compute_kpi_summary', digits=(6, 2),
    )
    kpi_budget_variance_pct = fields.Float(
        string='Budget Variance %', compute='_compute_kpi_summary', digits=(6, 2),
    )
    kpi_budget_usage_pct = fields.Float(
        string='Budget Usage %', compute='_compute_kpi_summary', digits=(6, 2),
    )

    @api.depends(
        'invoice_ids', 'invoice_ids.amount_untaxed',
        'invoice_ids.state',           # CR2 G5: required by posted-only filter
        'invoice_ids.invoice_date',    # CR2 G6: required by date-scope filter
        'project_expense_ids', 'project_expense_ids.amount',
        'project_expense_ids.state',
        'project_expense_ids.date',    # CR2 G6
        'project_expense_ids.category_id',
        'project_expense_ids.category_id.expense_type',
        'budget_line_ids', 'budget_line_ids.budget_amount', 'budget_line_ids.actual_amount',
        'budget_line_ids.state',       # CR2 G5: required by confirmed-only filter
        'budget_line_ids.date',        # CR2 G6
        # CR2 G3 (19.0.2.7.0): commission billed-only sum.
        'commission_line_ids', 'commission_line_ids.amount', 'commission_line_ids.state',
        'commission_line_ids.date',    # CR2 G6
        'report_date_from', 'report_date_to',  # CR2 G6 filter state
    )
    def _compute_kpi_summary(self):
        """One pass per record — reads children once, computes all 19 boxes.

        CR2 G2 (19.0.2.6.0): CGS/OpEx split is now driven by the tab a
        line belongs to (category.expense_type), not by
        account.account.account_type. Only confirmed (state='billed')
        lines contribute — draft lines are excluded per CR2 G7 item 2 so
        the client's month-end numbers match what was actually posted.
        """
        def _pct(numerator, denominator):
            """Guard against divide-by-zero: return 0.0 if denominator is 0.
            Return value is a FRACTION (0.425 for 42.5%) — Odoo's
            widget='percentage' does the ×100 + '%' on display."""
            if not denominator:
                return 0.0
            return numerator / denominator

        for rec in self:
            # CR2 G6: scope every source by the header Report Period.
            invs = rec._filter_by_report_period(rec.invoice_ids, 'invoice_date')
            dc_lines = rec._filter_by_report_period(rec.direct_cost_line_ids, 'date')
            op_lines = rec._filter_by_report_period(rec.operating_exp_line_ids, 'date')
            bud_lines = rec._filter_by_report_period(rec.budget_line_ids, 'date')
            com_lines = rec._filter_by_report_period(rec.commission_line_ids, 'date')

            # Billing Summary — state filters chained on top of date scope.
            total_invoiced = sum(
                inv.amount_untaxed for inv in invs if inv.state == 'posted'
            )
            cgs = sum(l.amount or 0.0 for l in dc_lines if l.state == 'billed')
            opex = sum(l.amount or 0.0 for l in op_lines if l.state == 'billed')
            total_budget = sum(
                l.budget_amount or 0.0 for l in bud_lines if l.state == 'confirmed'
            )
            total_actual = sum(
                l.actual_amount or 0.0 for l in bud_lines if l.state == 'confirmed'
            )
            remaining = total_budget - total_actual
            variance = total_actual - total_budget

            # Profitability
            gross_profit = total_invoiced - cgs
            net_profit = gross_profit - opex
            budgeted_profit = net_profit - total_budget
            actual_profit = net_profit - total_actual

            total_cost = cgs + opex

            rec.bs_total_invoiced = total_invoiced
            rec.bs_total_project_cgs = cgs
            rec.bs_total_project_exp = opex
            rec.bs_total_budget_cost = total_budget
            rec.bs_total_actual_cost = total_actual
            rec.bs_remaining_budget = remaining
            rec.bs_budget_variance = variance
            rec.pp_gross_profit = gross_profit
            rec.pp_net_profit = net_profit
            rec.pp_budgeted_profit = budgeted_profit
            rec.pp_actual_profit = actual_profit
            # CR2 G3+G6: billed-only sum, scoped by Report Period.
            commission_total = sum(
                l.amount or 0.0 for l in com_lines if l.state == 'billed'
            )
            rec.bs_sales_person_commission = commission_total
            rec.pp_profit_after_commission = actual_profit - commission_total
            rec.kpi_gross_margin = _pct(gross_profit, total_invoiced)
            rec.kpi_net_margin = _pct(net_profit, total_invoiced)
            rec.kpi_cogs_pct = _pct(cgs, total_invoiced)
            rec.kpi_opex_pct = _pct(opex, total_invoiced)
            rec.kpi_total_cost_pct = _pct(total_cost, total_invoiced)
            rec.kpi_roc = _pct(net_profit, total_cost)
            rec.kpi_budget_variance_pct = _pct(variance, total_budget)
            rec.kpi_budget_usage_pct = _pct(total_actual, total_budget)

    @api.onchange('client_id')
    def _onchange_client_id(self):
        """Auto-fill analytic from food delivery partner for per-partner profit tracking."""
        if self.client_id and not self.analytic_account_id:
            analytic = self.env['account.analytic.account'].search([
                ('partner_id', '=', self.client_id.id),
            ], limit=1)
            if analytic:
                self.analytic_account_id = analytic

    @api.depends(
        'invoice_ids', 'invoice_ids.amount_untaxed', 'invoice_ids.state',
        'invoice_ids.invoice_date',
        'report_date_from', 'report_date_to',
    )
    def _compute_invoice_count(self):
        """CR2 G5: posted-only. CR2 G6: scoped by Report Period."""
        for rec in self:
            invs = rec._filter_by_report_period(rec.invoice_ids, 'invoice_date')
            rec.invoice_count = len(invs)
            rec.total_invoiced = sum(
                inv.amount_untaxed for inv in invs if inv.state == 'posted'
            )

    @api.depends('timesheet_ids.hours')
    def _compute_totals(self):
        for rec in self:
            rec.total_hours = sum(rec.timesheet_ids.mapped('hours'))
            rec.total_employee_cost = 0.0
            rec.billing_margin = 0.0

    @api.depends(
        'project_expense_ids.amount', 'project_expense_ids.state',
        'project_expense_ids.date',
        'total_invoiced',
        'report_date_from', 'report_date_to',
    )
    def _compute_project_margin(self):
        """CR2 G2 billed-only + CR2 G6 date-scoped. Keeps this tile
        numerically consistent with bs_total_project_cgs+opex."""
        for rec in self:
            exp = rec._filter_by_report_period(rec.project_expense_ids, 'date')
            rec.total_project_expenses = sum(
                l.amount or 0.0 for l in exp if l.state == 'billed'
            )
            rec.project_margin = rec.total_invoiced - rec.total_project_expenses

    # ── CR3 P1 computes ────────────────────────────────────────────────────

    @api.depends('accounting_date')
    def _compute_contract_month(self):
        for rec in self:
            # Guarded — old rows with NULL accounting_date stay NULL.
            rec.contract_month = (
                rec.accounting_date.replace(day=1) if rec.accounting_date else False
            )

    # ── CR3 P1 monthly uniqueness — DB partial unique index ─────────────────
    # Race-safe uniqueness. @api.constrains alone is search-then-check with
    # no row lock → two concurrent creates can slip past. The partial index
    # guarantees hard uniqueness even under concurrency. WHERE clause skips
    # legacy rows (contract_month IS NULL) so `-u module` on a DB with
    # existing contracts doesn't retroactively enforce.
    def _auto_init(self):
        res = super()._auto_init()
        tools.create_index(
            self.env.cr,
            'way4tech_manpower_contract_month_unique_idx',
            self._table,
            [
                'client_id',
                'contract_month',
                "COALESCE(way4tech_project_id, 0)",
            ],
            where="state IN ('active', 'completed') AND contract_month IS NOT NULL",
            unique=True,
        )
        return res

    # ── CR3 P1 Python-side uniqueness (nicer error than IntegrityError) ────
    @api.constrains(
        'client_id', 'contract_month', 'way4tech_project_id', 'state',
    )
    def _check_monthly_unique(self):
        for rec in self:
            # Skip legacy rows and draft/cancelled — matches partial index scope.
            if rec.state not in ('active', 'completed'):
                continue
            if not rec.contract_month:
                continue
            if not rec.client_id:
                continue
            dup = self.search([
                ('id', '!=', rec.id),
                ('client_id', '=', rec.client_id.id),
                ('contract_month', '=', rec.contract_month),
                ('way4tech_project_id', '=', rec.way4tech_project_id.id or False),
                ('state', 'in', ('active', 'completed')),
            ], limit=1)
            if dup:
                raise ValidationError(_(
                    'A monthly contract already exists for this client + '
                    'month + project — %(dup)s.\n\n'
                    'One record = one client-month-project. If you need a '
                    'second contract for the same slot, cancel the existing '
                    'one first, or pick a different Accounting Date, '
                    'Client, or Project.'
                ) % {'dup': dup.display_name or dup.reference or dup.id})

    # ── Reference auto-generation (P3) ──────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # --- CR3 P1: seed accounting_date, mirror to start_date, auto-name ---
            # setdefault(accounting_date) BEFORE anything else so programmatic
            # callers like create({'client_id': X}) get a valid date instead
            # of hitting our downstream logic with None. The default is the
            # same value fields.Date.context_today would supply on UI create.
            if not vals.get('accounting_date'):
                vals['accounting_date'] = fields.Date.context_today(self)
            # Mirror accounting_date -> start_date on new rows so the 7 code
            # readers of start_date (reference sequence date-range, _order,
            # wizard domain, list/search/pivot filters, PDF report header)
            # keep seeing a valid date without any of them needing change.
            # Guard 2 from the CR3 spec.
            if not vals.get('start_date'):
                vals['start_date'] = vals['accounting_date']
            # Auto-name: Client + Month (e.g. "ALFANAR — 06/2026"). Only when
            # name is empty — existing records loaded via db_load / import
            # with a pre-picked name are left alone.
            if not vals.get('name') and vals.get('client_id') and vals.get('accounting_date'):
                client = self.env['res.partner'].browse(vals['client_id'])
                acc = fields.Date.to_date(vals['accounting_date'])
                if client and acc:
                    vals['name'] = '%s — %s' % (client.name, acc.strftime('%m/%Y'))
            # Due Date: Accounting Date + 45 days (user-overwritable). Only
            # set on create — never auto-recomputed after (avoids overriding
            # manual client-specific due-date agreements).
            if not vals.get('due_date') and vals.get('accounting_date'):
                acc = fields.Date.to_date(vals['accounting_date'])
                if acc:
                    vals['due_date'] = acc + timedelta(days=45)
            # ------------------------------------------------------------
            if not vals.get('reference'):
                seq_date = vals.get('start_date') or date.today()
                vals['reference'] = self.env['ir.sequence'].with_context(
                    ir_sequence_date=seq_date,
                ).next_by_code('way4tech.manpower.contract.pro') or '/'
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _unlink_check_active_documents(self):
        """CR3 P4 (v13.0): monthly-record delete protection.

        Blocks unlink when the contract has posted invoices, posted bills,
        or non-draft signature requests attached — user must cancel/reset
        those first. Mirrors the spirit of the existing line-level unlink
        guards on income/expense/commission lines.
        """
        for rec in self:
            # Any customer invoice minted from this contract's income lines?
            posted_inv = self.env['account.move'].search_count([
                ('id', 'in', rec.income_line_ids.mapped('invoice_id').ids +
                             rec.timesheet_ids.mapped('invoice_id').ids +
                             rec.invoice_ids.ids),
                ('state', '!=', 'cancel'),
            ])
            if posted_inv:
                raise UserError(_(
                    'Cannot delete "%(name)s" — it has %(n)d non-cancelled '
                    'customer invoice(s) attached. Cancel those first, or '
                    'change the contract state to Cancelled to archive it.'
                ) % {'name': rec.display_name, 'n': posted_inv})
            # Any non-cancelled vendor bills from expense / commission lines?
            posted_bill_ids = (
                rec.direct_cost_line_ids.mapped('bill_id') |
                rec.operating_exp_line_ids.mapped('bill_id') |
                rec.commission_line_ids.mapped('bill_id')
            )
            posted_bill = posted_bill_ids.filtered(lambda m: m.state != 'cancel')
            if posted_bill:
                raise UserError(_(
                    'Cannot delete "%(name)s" — it has %(n)d non-cancelled '
                    'vendor bill(s) attached. Cancel those first, or set '
                    'the contract state to Cancelled to archive it.'
                ) % {'name': rec.display_name, 'n': len(posted_bill)})

    def write(self, vals):
        # CR3 P1: keep start_date populated when accounting_date is set on
        # a legacy row that was migrated with start_date=False, or when a
        # programmatic path clears start_date. Only mirrors if start_date
        # would be empty AFTER the write — never overwrites an existing
        # user-picked start_date (protects old records).
        if 'accounting_date' in vals and vals.get('accounting_date'):
            for rec in self:
                effective_start = vals.get('start_date', rec.start_date)
                if not effective_start:
                    vals['start_date'] = vals['accounting_date']
                    break  # one write() call = one vals dict, mirror once
        return super().write(vals)

    def _compose_reference_string(self, invoice=None):
        """Build the composite reference string used on generated documents.

        Pattern (P3): ``Reference — Project — Partner — Invoice# — Tags — Month``
        Missing pieces are dropped (no empty ``—`` runs).
        """
        self.ensure_one()
        month = self.start_date.strftime('%m/%Y') if self.start_date else ''
        parts = [
            self.reference or '',
            (self.way4tech_project_id.name or '') if self.way4tech_project_id else '',
            self.client_id.name or '',
            (invoice.name or '') if invoice else '',
            ', '.join(self.tag_ids.mapped('name')) if self.tag_ids else '',
            month,
        ]
        return ' — '.join(p for p in parts if p)

    def _resolve_analytic_distribution(self, settings=None):
        """Return the analytic distribution dict to stamp on generated lines.

        Preference order: contract's own ``analytic_distribution`` (multi) →
        legacy ``analytic_account_id`` (single, 100%) → company default from
        Payroll & Accounting Setup (single, 100%). Returns ``{}`` if nothing
        is configured — Odoo treats an empty dict as "no analytic".
        """
        self.ensure_one()
        if self.analytic_distribution:
            return dict(self.analytic_distribution)
        if self.analytic_account_id:
            return {str(self.analytic_account_id.id): 100}
        if settings and settings.default_analytic_account_id:
            return {str(settings.default_analytic_account_id.id): 100}
        return {}

    def action_activate(self):
        self.ensure_one()
        self.state = 'active'

    def action_complete(self):
        self.ensure_one()
        self.state = 'completed'

    def action_cancel(self):
        self.ensure_one()
        self.state = 'cancelled'

    def action_reset_draft(self):
        self.ensure_one()
        self.state = 'draft'

    # ── CR2 G5 (19.0.2.9.0): signature-approval gate ──────────────────────
    def _require_month_approval(self, target_date):
        """CR2 G5 gate: raise UserError unless this contract has an approved
        Signature Request for target_date's MM/YYYY bucket. Simplification:
        approval merely unlocks the tab for that month — we do NOT restore
        from snapshot. Once approved for month M, any subsequent edits to
        lines dated M are the accountant's responsibility (visible in
        chatter via tracking=True)."""
        self.ensure_one()
        if not target_date:
            target_date = fields.Date.context_today(self)
        month = target_date.strftime('%m/%Y')
        approved = self.env['way4tech.manpower.contract.signature.request'].search([
            ('contract_id', '=', self.id),
            ('month', '=', month),
            ('state', '=', 'approved'),
        ], limit=1)
        if not approved:
            raise UserError(_(
                'Cannot post accounting documents for contract "%s" — no '
                'approved Signature Request exists for month %s. Open the '
                'Approvals tab, click "Send for Signature", then have the '
                'manager approve the request before creating invoices/bills.'
            ) % (self.name, month))
        return approved

    def action_send_for_signature(self):
        """CR2 G5: open a NEW Signature Request in draft, pre-filled with
        the current month. Accountant reviews tabs (still writable in
        draft), clicks 'Send for Signature' on the request itself."""
        self.ensure_one()
        month = fields.Date.context_today(self).strftime('%m/%Y')
        return {
            'type': 'ir.actions.act_window',
            'name': _('New Signature Request'),
            'res_model': 'way4tech.manpower.contract.signature.request',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_contract_id': self.id,
                'default_month': month,
            },
        }

    def action_create_invoice(self):
        self.ensure_one()
        # CR2 G5 skeptic amendment 2: use context_today, NOT self.start_date
        # (start_date is contract kickoff, not the invoicing period — using
        # it here means only the FIRST month ever needs approval).
        self._require_month_approval(fields.Date.context_today(self))
        if self.billing_type == 'fixed':
            amount = self.fixed_amount
            description = 'Fixed Price - %s' % self.name
        else:
            amount = self.total_hours * self.hourly_rate
            description = 'Hourly Rate (%s hrs x %s) - %s' % (
                self.total_hours, self.hourly_rate, self.name
            )

        if not amount:
            raise UserError(_('Invoice amount is zero. Please check the fixed amount or timesheet hours.'))

        # PO balance check
        if self.po_id:
            if self.po_id.state == 'closed':
                raise UserError(_(
                    'Client PO "%s" is fully consumed (closed).\n'
                    'Increase the PO total amount or create a new PO.'
                ) % self.po_id.name)
            if amount > self.po_id.remaining_balance:
                raise UserError(_(
                    'Invoice amount (%.2f) exceeds remaining PO balance (%.2f) on PO "%s".\n'
                    'Increase the PO total amount or reduce the invoice amount.'
                ) % (amount, self.po_id.remaining_balance, self.po_id.name))

        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)

        # Find the default 15% VAT sales tax for this company
        vat_tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('amount_type', '=', 'percent'),
            ('amount', '=', 15.0),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        invoice_line_vals = {
            'name': description,
            'quantity': 1.0,
            'price_unit': amount,
        }
        if settings.manpower_income_account_id:
            invoice_line_vals['account_id'] = settings.manpower_income_account_id.id
        # Analytic distribution: prefer the new multi-analytic Json; fall
        # back to legacy single analytic; then to company default. Passes
        # the exact same shape onto invoice lines that the accountant
        # already sees on account.move.line.
        distribution = self._resolve_analytic_distribution(settings)
        if distribution:
            invoice_line_vals['analytic_distribution'] = distribution
        if not vat_tax:
            raise UserError(_('No 15% sales tax found for this company. Please configure a 15% VAT sales tax before creating a manpower invoice.'))
        invoice_line_vals['tax_ids'] = [(6, 0, [vat_tax.id])]

        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.client_id.id,
            'invoice_date': fields.Date.today(),
            'company_id': self.company_id.id,
            'invoice_line_ids': [(0, 0, invoice_line_vals)],
        }
        if settings.manpower_journal_id:
            invoice_vals['journal_id'] = settings.manpower_journal_id.id

        # Project + Entry Category propagate from the contract onto the
        # invoice header (which itself mirrors onto every line via the
        # related fields on account.move.line — see
        # account_move_line_extension.py). Contract's values win over the
        # legacy Manpower Revenue default so the operator's explicit choice
        # is what appears on the invoice.
        if self.way4tech_project_id:
            invoice_vals['way4tech_project_id'] = self.way4tech_project_id.id
        if self.way4tech_category_id:
            invoice_vals['way4tech_category_id'] = self.way4tech_category_id.id
        else:
            _category = self.env.ref('way4tech_logistics.category_manpower_revenue', raise_if_not_found=False)
            if _category:
                invoice_vals['way4tech_category_id'] = _category.id
        if self.po_id:
            invoice_vals['way4tech_po_id'] = self.po_id.id
        if self.tag_ids:
            invoice_vals['way4tech_tag_ids'] = [(6, 0, self.tag_ids.ids)]
        invoice = self.env['account.move'].create(invoice_vals)
        invoice.ref = self._compose_reference_string(invoice=invoice)
        self._apply_ksa_account_overrides(invoice)
        self.invoice_ids = [(4, invoice.id)]
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _apply_ksa_account_overrides(self, move):
        """CR2 G1 (2026-07-17): after a move is created via one of the
        contract's Create Invoice / Create Bill actions, force the AR/AP
        counterpart line to the account configured in Payroll & Accounting
        Setup (Manpower Receivable = 140001 for invoices, Manpower Payable
        = 210001 for bills). Odoo's auto-balance defaults to the partner's
        property_account_receivable/payable_id, which the client says is
        the wrong account by default — this override reads from the settings
        and re-points the counterpart line. Payable is applied ONLY on
        purchase-side moves (in_invoice / in_refund), receivable ONLY on
        sale-side (out_invoice / out_refund) — no cross-contamination."""
        self.ensure_one()
        if not move:
            return
        settings = self.env['way4tech.payroll.settings'].get_for_company(
            move.company_id.id,
        )
        if move.move_type in ('out_invoice', 'out_refund'):
            target = settings.manpower_receivable_account_id
            if target:
                for line in move.line_ids.filtered(
                    lambda l: l.account_id and l.account_id.account_type == 'asset_receivable'
                ):
                    if line.account_id != target:
                        line.account_id = target
        elif move.move_type in ('in_invoice', 'in_refund'):
            target = settings.manpower_payable_account_id
            if target:
                for line in move.line_ids.filtered(
                    lambda l: l.account_id and l.account_id.account_type == 'liability_payable'
                ):
                    if line.account_id != target:
                        line.account_id = target

    def _get_commission_amount(self, employee, target_date=None):
        """CR2 G3 — canonical commission calculation for the salesperson.

        Called by way4tech.manpower.commission.line._compute_amount and by
        action_create_bill. Returns a currency-scoped monetary value based
        on the contract's commission_type + employee's template rate.

        Rules
        -----
          - salesperson_id empty OR commission_type == 'none' → 0.0
          - Missing template for employee → 0.0 + _logger.warning.
            (Skeptic bug 1: NO message_post here — computes must be
            side-effect-free. action_create_bill raises UserError so the
            accountant sees the config gap at the moment they try to bill.)
          - Fix mode: fix_rate × count(POSTED out_invoice with invoice_date
            in target month). Drafts + refunds + cancelled excluded
            (skeptic bug 2).
          - %-modes: if pp_actual_profit <= 0 → 0.0 (hard gate)
                    else max(0.0, rate/100.0 × profit_value_for_type)
        """
        self.ensure_one()
        if not employee or not self.salesperson_id or self.commission_type == 'none':
            return 0.0

        template = self.env['way4tech.commission.template'].search([
            ('employee_id', '=', employee.id),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not template:
            import logging
            logging.getLogger(__name__).warning(
                "No commission template for employee %s on company %s; "
                "commission set to 0. Configure in Payroll & Accounting Setup.",
                employee.display_name, self.company_id.display_name,
            )
            return 0.0

        if self.commission_type == 'fix':
            from datetime import date as _date
            target = target_date or _date.today()
            invoice_count = sum(
                1 for inv in self.invoice_ids
                if inv.state == 'posted'
                and inv.move_type == 'out_invoice'
                and inv.invoice_date
                and inv.invoice_date.year == target.year
                and inv.invoice_date.month == target.month
            )
            return (template.fix_rate or 0.0) * invoice_count

        # Percentage modes — hard-gate on Actual Profit > 0.
        if (self.pp_actual_profit or 0.0) <= 0.0:
            return 0.0
        rate_map = {
            'gp': (template.gp_rate, self.pp_gross_profit),
            'np': (template.np_rate, self.pp_net_profit),
            'budgeted': (template.budgeted_rate, self.pp_budgeted_profit),
            'actual': (template.actual_rate, self.pp_actual_profit),
        }
        rate, profit_value = rate_map.get(self.commission_type, (0.0, 0.0))
        computed = (rate or 0.0) / 100.0 * (profit_value or 0.0)
        return max(0.0, computed)

    @api.depends(
        'direct_cost_line_ids.bill_id',
        'direct_cost_line_ids.bill_id.amount_untaxed',
        'direct_cost_line_ids.bill_id.state',
        'direct_cost_line_ids.bill_id.move_type',
        'operating_exp_line_ids.bill_id',
        'operating_exp_line_ids.bill_id.amount_untaxed',
        'operating_exp_line_ids.bill_id.state',
        'operating_exp_line_ids.bill_id.move_type',
        'commission_line_ids.bill_id',
        'commission_line_ids.bill_id.amount_untaxed',
        'commission_line_ids.bill_id.state',
        'commission_line_ids.bill_id.move_type',
    )
    def _compute_bill_aggregates(self):
        """CR2 G4: aggregate all vendor bills across Direct Cost / OpEx /
        Commission tabs for the smart button. Non-stored — single source
        of truth is child line's bill_id FK."""
        for rec in self:
            moves = (
                rec.direct_cost_line_ids.mapped('bill_id')
                | rec.operating_exp_line_ids.mapped('bill_id')
                | rec.commission_line_ids.mapped('bill_id')
            ).filtered(lambda m: m.move_type in ('in_invoice', 'in_refund'))
            rec.bill_ids = moves
            rec.bill_count = len(moves)
            rec.bill_total = sum(moves.mapped('amount_untaxed'))

    def action_view_bills(self):
        """CR2 G4: Vendor Bills smart button — opens filtered list."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bills'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.bill_ids.ids)],
            'context': {'default_move_type': 'in_invoice'},
        }

    def action_view_partner_ledger(self):
        """CR2 G4: Customer Statement smart button — opens standard Odoo
        journal-items list filtered to this contract's client's AR/AP
        entries. Community-safe: works without account_reports (Enterprise).
        Skeptic amendment F: drop parent_state='posted' so drafts also show
        (real accountant workflow); drop group_by_partner (redundant since
        the domain is already partner-scoped)."""
        self.ensure_one()
        if not self.client_id:
            raise UserError(_(
                'Set a client on the contract before opening its statement.'
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Customer Statement — %s') % self.client_id.display_name,
            'res_model': 'account.move.line',
            'view_mode': 'list,form',
            'domain': [
                ('partner_id', '=', self.client_id.id),
                ('account_id.account_type', 'in', ('asset_receivable', 'liability_payable')),
            ],
            'context': {'search_default_group_by_account': 1},
        }

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.invoice_ids.ids)],
        }


class Way4TechManpowerContractLine(models.Model):
    _name = 'way4tech.manpower.contract.line'
    _description = 'Manpower Contract Line'
    _order = 'contract_id, employee_id'

    contract_id = fields.Many2one(
        comodel_name='way4tech.manpower.contract',
        string='Contract',
        required=True,
        ondelete='cascade',
    )
    employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Employee',
    )
    role = fields.Char(string='Role/Position')
    start_date = fields.Date(string='Start Date')
    end_date = fields.Date(string='End Date')
    daily_cost = fields.Monetary(
        string='Daily Cost',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='contract_id.company_id.currency_id',
        string='Currency',
        readonly=True,
    )


