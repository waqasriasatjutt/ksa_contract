from datetime import date

from odoo import api, fields, models, tools, _
from odoo.exceptions import UserError, ValidationError


class Way4TechManpowerContract(models.Model):
    _name = 'way4tech.manpower.contract'
    _description = 'Manpower Billing Contract'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    # CR3-FINAL P1: Start Date is the record's period start and the primary
    # date of the monthly record. accounting_date is kept in the model and
    # mirrored FROM start_date (see create/write) purely so external readers
    # and legacy data keep resolving — it is no longer the driver.
    _order = 'start_date desc, id desc'

    # CR3-FINAL P8: no longer required — auto-generated as "Client — MM/YYYY"
    # from client_id + start_date's month in create(). Left writable so a user
    # can still override, and existing names are never touched.
    name = fields.Char(
        string='Contract Name', tracking=True,
        help='Auto-generated as "Client — MM/YYYY" from the Client and the '
             'Start Date month when left blank. Existing names are preserved.',
    )
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
    # CR3-FINAL P5: aggregator=None keeps these OUT of the pivot's Measures
    # dropdown. They are per-record settings/rates, not summable totals —
    # summing "Hourly Rate" across contracts is meaningless.
    fixed_amount = fields.Monetary(
        string='Fixed Monthly Amount',
        currency_field='currency_id',
        aggregator=None,
    )
    hourly_rate = fields.Monetary(
        string='Hourly Rate',
        currency_field='currency_id',
        aggregator=None,
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
        # CR3-FINAL P5: a per-record setting, not a summable total.
        aggregator=None,
        help='Per-day allowed hours for timesheet rows on this contract. '
             'Auto-fills timesheet.per_day_hours when an employee is picked '
             '(only when the timesheet row is still blank). Overrides the '
             'employee-level default; line-level override still wins.',
    )
    # ── CR3-FINAL P1: Start/End Date are THE header period of the record ──
    # The record's month (auto-name, PRO reference series, uniqueness key)
    # all derive from start_date's month. Line-level dates are untouched —
    # every Income / Expense / Timesheet / Budget / Commission row keeps its
    # own date, and month grouping in reports uses the LINE/invoice date,
    # never this header.
    start_date = fields.Date(
        string='Start Date', required=True,
        default=fields.Date.context_today,
        index=True,
        tracking=True,
        help="Start of this record's period. Drives the auto-name "
             '(Client — MM/YYYY), the PRO/YYYY/MM/NNNN reference series and '
             'the one-record-per-client-month-project uniqueness rule.',
    )
    end_date = fields.Date(
        string='End Date',
        tracking=True,
        help="End of this record's period. Display/reporting only — it does "
             'not affect the month key or the reference series.',
    )

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
    # CR3-FINAL P1: DEMOTED. Removed from the form header (Start/End Date
    # replaced it) but kept in the model and mirrored FROM start_date in
    # create()/write() so every existing reader — the optional list column,
    # the search filters, external references and legacy rows — keeps
    # resolving without a data migration. Never drives anything now.
    accounting_date = fields.Date(
        string='Accounting Date (legacy)',
        index=True,
        tracking=True,
        help='Legacy mirror of Start Date, kept for backwards compatibility '
             'with existing filters and saved views. The header period is now '
             'Start Date + End Date.',
    )
    # First-day-of-month normalisation of START DATE (CR3-FINAL P1 re-key).
    # Stored + indexed so it can back the DB-level partial unique index built
    # in _auto_init.
    contract_month = fields.Date(
        string='Month',
        compute='_compute_contract_month',
        store=True,
        index=True,
        help="First day of Start Date's month. Used as the uniqueness key "
             'together with client and project.',
    )
    # CR3-FINAL P1: the +45-day auto-fill is REMOVED per client instruction.
    # Field retained (never dropped — "hide" means remove from the view only)
    # so historical values stay readable and no column is destroyed.
    due_date = fields.Date(
        string='Due Date (legacy)',
        help='Legacy field. The automatic Accounting Date + 45 days default '
             'was removed in CR3-FINAL P1; existing values are preserved.',
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
    # CR3-FINAL round 2, bug 3: both of these are hard-wired to 0.0 in
    # _compute_totals and have been for some time, so they showed up in the
    # Measures dropdown as permanent zeros. aggregator=None takes them out of
    # the measure list; the columns stay so nothing that reads them breaks.
    total_employee_cost = fields.Monetary(
        string='Total Employee Cost (unused)',
        compute='_compute_totals',
        store=True,
        aggregator=None,
        currency_field='currency_id',
        help="Not in use — always 0. Employee salary cost is tracked on the "
             "Project Direct Cost tab instead.",
    )
    billing_margin = fields.Monetary(
        string='Billing Margin (unused)',
        compute='_compute_totals',
        store=True,
        aggregator=None,
        currency_field='currency_id',
        help="Not in use — always 0. Superseded by the Project Profitability "
             "figures.",
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
    # ── CR3-FINAL P11: live balance shown under the Customer Statement button
    client_balance = fields.Monetary(
        string='Client Balance', compute='_compute_client_balance',
        currency_field='currency_id',
        help="The client's live outstanding balance — the same closing "
             'balance the Partner Ledger reports. Signed sum of posted '
             'receivable and payable journal items. Recomputed on every read, '
             'so it follows invoices and payments automatically.',
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
    # ── CR3-FINAL P6: multi-line invoices built from the contract ─────────
    invoice_block_ids = fields.One2many(
        'way4tech.manpower.invoice.block',
        'contract_id',
        string='Invoice Blocks',
        help='Each block is one future customer invoice. Add several lines '
             'to a block and its Create Invoice button bills them all on a '
             'single document. A month can hold several blocks.',
    )
    # Income rows that predate invoice blocks, or were typed straight onto
    # the flat grid. Shown in their own section so nothing created before
    # P6 disappears from the form.
    unassigned_income_line_ids = fields.One2many(
        'way4tech.manpower.contract.income.line',
        'contract_id',
        domain=[('invoice_block_id', '=', False)],
        string='Income Lines (not in a block)',
    )
    unassigned_income_count = fields.Integer(
        compute='_compute_unassigned_income_count',
    )

    @api.depends('income_line_ids', 'income_line_ids.invoice_block_id')
    def _compute_unassigned_income_count(self):
        for rec in self:
            rec.unassigned_income_count = len(
                rec.income_line_ids.filtered(lambda l: not l.invoice_block_id)
            )
    budget_line_ids = fields.One2many(
        'way4tech.manpower.contract.budget.line',
        'contract_id',
        string='Project Budget',
    )
    # CR3-FINAL round 2, bug 3: this is the OLD all-buckets total and is
    # duplicated by bs_total_project_exp_all ("Total Project Exp"). It shared
    # the label "Total Project Expenses" with bs_total_project_exp, which is
    # what put two different numbers under one name in the Measures dropdown.
    # Renamed and dropped from the measure list; the field itself stays
    # because the list view and older reports still read it.
    total_project_expenses = fields.Monetary(
        string='Total Project Expenses (legacy)',
        compute='_compute_project_margin',
        store=True,
        aggregator=None,
        currency_field='currency_id',
        help='Legacy all-buckets expense total. Use "Total Project Exp" '
             '(Direct Cost + Operating Expenses) instead.',
    )
    project_margin = fields.Monetary(
        string='Project Margin (legacy)',
        compute='_compute_project_margin',
        store=True,
        aggregator=None,
        currency_field='currency_id',
        help='Project Margin = Total Invoiced − Total Project Expenses.\n'
             'Positive = profitable. Shows the gross margin before company overhead.\n'
             'For full P&L including individual salary costs, see the Analytic Report.',
    )
    notes = fields.Text(string='Notes')

    # ══ CR3-FINAL P2/P3/P4/P5: Billing Summary + Project Profitability + KPI%
    #
    # P5 (client's core demand): every box below is now STORED so it appears
    # in the pivot's Measures dropdown and can be grouped/rolled up. Values
    # are computed ONCE here at contract level; the pivot, list, statement and
    # PDF only DISPLAY them — nothing recalculates downstream.
    #
    # KPI % fields hold a PERCENTAGE NUMBER (18.10 == 18.10%), not a fraction,
    # and carry no widget="percentage". That is deliberate: widget=percentage
    # renders a 0.181 fraction as "18.10%" on the form while the pivot would
    # show the raw 0.18 — breaking the master rule that record value must
    # equal pivot value must equal list value. Storing the percentage number
    # makes all three read 18.10.
    #
    # Two compute methods, NOT one — this is a hard requirement, not style.
    # way4tech.manpower.commission.line._compute_amount depends on
    # contract.pp_gross_profit / pp_net_profit / pp_budgeted_profit /
    # pp_actual_profit. If the commission totals were computed in the SAME
    # method as those profits, storing them would create a dependency cycle
    # (commission amount → contract profit → commission total → …) and Odoo
    # would recurse. Group 1 below therefore depends only on invoices,
    # expenses and budget; group 2 depends on commission lines plus group 1.
    # ═══════════════════════════════════════════════════════════════════════

    # Map of KPI% field → (numerator field, denominator field). Drives the
    # group-level recalculation in _read_group so a percentage is never
    # summed across a group (P5 aggregation rule).
    PERCENT_MEASURES = {
        'kpi_gross_margin': ('pp_gross_profit', 'bs_total_invoiced'),
        'kpi_net_margin': ('pp_net_profit', 'bs_total_invoiced'),
        'kpi_cogs_pct': ('bs_total_project_cgs', 'bs_total_invoiced'),
        'kpi_opex_pct': ('bs_total_project_exp', 'bs_total_invoiced'),
        'kpi_total_cost_pct': ('bs_total_project_exp_all', 'bs_total_invoiced'),
        'kpi_roc': ('pp_net_profit', 'bs_total_project_exp_all'),
        'kpi_budget_variance_pct': ('bs_budget_variance', 'bs_total_budget_cost'),
        'kpi_budget_usage_pct': ('bs_total_actual_cost', 'bs_total_budget_cost'),
        'kpi_net_return_on_cost_after_commission': (
            'pp_profit_after_commission', 'bs_total_project_exp_all',
        ),
    }

    # ── Group 1: Billing Summary + Profitability (no commission input) ─────
    bs_total_invoiced = fields.Monetary(
        string='Total Invoiced', compute='_compute_kpi_summary',
        store=True, currency_field='currency_id',
        help='Sum of untaxed amounts on POSTED customer invoices linked to '
             'this contract.',
    )
    bs_total_project_cgs = fields.Monetary(
        string='Total Project CGS', compute='_compute_kpi_summary',
        store=True, currency_field='currency_id',
        help='Direct Cost (COGS): sum of billed Project Expense lines whose '
             'category is bucketed as Direct Cost.',
    )
    # CR3-FINAL round 2, bug 3: renamed. This holds OPERATING EXPENSES only,
    # but was labelled "Total Project Expenses" — the same label as the legacy
    # total_project_expenses field below, so the Measures dropdown showed two
    # different numbers under one identical name (900 here vs 4,510 there).
    bs_total_project_exp = fields.Monetary(
        string='Operating Expenses', compute='_compute_kpi_summary',
        store=True, currency_field='currency_id',
        help='Operating Expenses: sum of billed Project Expense lines whose '
             'category is bucketed as Operating Exp. Direct Cost is reported '
             'separately as Total Project CGS; the two together are Total '
             'Project Exp.',
    )
    # ── CR3-FINAL P3: new field ───────────────────────────────────────────
    bs_total_project_exp_all = fields.Monetary(
        string='Total Project Exp', compute='_compute_kpi_summary',
        store=True, currency_field='currency_id',
        help='Total Project Exp = Total Direct Cost (COGS) + Total Operating '
             'Expenses. Example: 3,000 + 800 = 3,800.',
    )
    bs_total_budget_cost = fields.Monetary(
        string='Total Budget Cost', compute='_compute_kpi_summary',
        store=True, currency_field='currency_id',
    )
    bs_total_actual_cost = fields.Monetary(
        string='Total Actual Cost', compute='_compute_kpi_summary',
        store=True, currency_field='currency_id',
    )
    bs_remaining_budget = fields.Monetary(
        string='Remaining Budget', compute='_compute_kpi_summary',
        store=True, currency_field='currency_id',
    )
    bs_budget_variance = fields.Monetary(
        string='Budget Variance', compute='_compute_kpi_summary',
        store=True, currency_field='currency_id',
    )
    pp_gross_profit = fields.Monetary(
        string='Gross Profit', compute='_compute_kpi_summary',
        store=True, currency_field='currency_id',
        help='Gross Profit = Income − COGS.',
    )
    pp_net_profit = fields.Monetary(
        string='Net Profit', compute='_compute_kpi_summary',
        store=True, currency_field='currency_id',
        help='Net Profit = Gross Profit − Operating Expenses.',
    )
    # CR3-FINAL P2 fix 1. Field NAME kept (commission model depends on it and
    # renaming the column would be destructive); label + formula corrected.
    pp_budgeted_profit = fields.Monetary(
        string='Profit After Budget', compute='_compute_kpi_summary',
        store=True, currency_field='currency_id',
        help='Profit After Budget = Income − COGS − Budget Cost '
             '(= Gross Profit − Budget Cost). Operating Expenses are NOT '
             'subtracted here. Example: 5,000 − 3,000 − 1,000 = 1,000.',
    )
    # CR3-FINAL P2 fix 2.
    pp_actual_profit = fields.Monetary(
        string='Profit After Actual Cost', compute='_compute_kpi_summary',
        store=True, currency_field='currency_id',
        help='Profit After Actual Cost = Income − COGS − Actual Cost '
             '(= Gross Profit − Actual Cost). Operating Expenses are NOT '
             'subtracted here. Example: 5,000 − 3,000 − 800 = 1,200.',
    )
    kpi_gross_margin = fields.Float(
        string='Gross Margin %', compute='_compute_kpi_summary',
        store=True, digits=(6, 2),
    )
    kpi_net_margin = fields.Float(
        string='Net Margin %', compute='_compute_kpi_summary',
        store=True, digits=(6, 2),
    )
    kpi_cogs_pct = fields.Float(
        string='COGS %', compute='_compute_kpi_summary',
        store=True, digits=(6, 2),
    )
    kpi_opex_pct = fields.Float(
        string='Operating Expense %', compute='_compute_kpi_summary',
        store=True, digits=(6, 2),
    )
    kpi_total_cost_pct = fields.Float(
        string='Total Cost %', compute='_compute_kpi_summary',
        store=True, digits=(6, 2),
    )
    kpi_roc = fields.Float(
        string='Profit to Cost (ROC) %', compute='_compute_kpi_summary',
        store=True, digits=(6, 2),
    )
    kpi_budget_variance_pct = fields.Float(
        string='Budget Variance %', compute='_compute_kpi_summary',
        store=True, digits=(6, 2),
    )
    kpi_budget_usage_pct = fields.Float(
        string='Budget Usage %', compute='_compute_kpi_summary',
        store=True, digits=(6, 2),
    )

    # ── Group 2: commission-derived boxes (depend on group 1 + commission) ─
    bs_sales_person_commission = fields.Monetary(
        string='Total Salesperson Commission',
        compute='_compute_commission_kpis',
        store=True, currency_field='currency_id',
        help='Sum of commission-line amounts whose vendor bill has been '
             "created (state='billed') — consistent with the billed-only "
             'rule applied to CGS/OpEx, so the tiles match the GL.',
    )
    # CR3-FINAL round 2, bug 1: base is PROFIT AFTER ACTUAL COST.
    # The first spec said "Net Profit − Commission" and gave 1,200 − 512 = 688,
    # so that is what shipped. Testing against the client's reference sheet
    # showed the real rule is F23 = F22 − B26, i.e. Profit After Actual Cost −
    # Commission. The two only agree when Operating Expenses happen to equal
    # Actual Cost, which is exactly why the first example did not expose it.
    pp_profit_after_commission = fields.Monetary(
        string='Net Profit After Salesperson Commission',
        compute='_compute_commission_kpis',
        store=True, currency_field='currency_id',
        help='Net Profit After Salesperson Commission = Profit After Actual '
             'Cost − Commission. Example: 1,500 − 512 = 988.',
    )
    # ── CR3-FINAL P4: new KPI ─────────────────────────────────────────────
    kpi_net_return_on_cost_after_commission = fields.Float(
        string='Net Return on Cost After Commission %',
        compute='_compute_commission_kpis', store=True, digits=(6, 2),
        help='Net Profit After Commission ÷ (Total Direct Cost + Total '
             'Operating Expenses), as a percentage. Example: '
             '688 ÷ 3,800 ≈ 18.11%. Zero cost → 0%.',
    )

    @staticmethod
    def _kpi_pct(numerator, denominator):
        """Percentage NUMBER (18.10 for 18.10%), divide-by-zero → 0.0."""
        if not denominator:
            return 0.0
        return (numerator / denominator) * 100.0

    @api.depends(
        'invoice_ids', 'invoice_ids.amount_untaxed', 'invoice_ids.state',
        # Depend on the UNDOMAINED o2m + the discriminator, then split in
        # Python below. Depending on the domained direct_cost_line_ids /
        # operating_exp_line_ids instead would make stored-field invalidation
        # unreliable — Odoo does not re-evaluate an o2m domain when the
        # category's expense_type changes on an existing line.
        'project_expense_ids', 'project_expense_ids.amount',
        'project_expense_ids.state',
        'project_expense_ids.category_id',
        'project_expense_ids.category_id.expense_type',
        'budget_line_ids', 'budget_line_ids.budget_amount',
        'budget_line_ids.actual_amount', 'budget_line_ids.state',
    )
    def _compute_kpi_summary(self):
        """Group 1 — one pass per record over invoices / expenses / budget.

        Only POSTED invoices, BILLED expense lines and CONFIRMED budget lines
        contribute, so the month-end figures always match what reached the GL.
        """
        for rec in self:
            total_invoiced = sum(
                inv.amount_untaxed for inv in rec.invoice_ids
                if inv.state == 'posted'
            )
            cgs = opex = 0.0
            for line in rec.project_expense_ids:
                if line.state != 'billed':
                    continue
                bucket = line.category_id.expense_type
                if bucket == 'direct':
                    cgs += line.amount or 0.0
                elif bucket == 'operating':
                    opex += line.amount or 0.0
            total_budget = sum(
                l.budget_amount or 0.0 for l in rec.budget_line_ids
                if l.state == 'confirmed'
            )
            total_actual = sum(
                l.actual_amount or 0.0 for l in rec.budget_line_ids
                if l.state == 'confirmed'
            )
            total_cost = cgs + opex

            # ── CR3-FINAL P2: corrected profitability formulas ──
            gross_profit = total_invoiced - cgs            # Income − COGS
            net_profit = gross_profit - opex               # GP − OpEx
            profit_after_budget = gross_profit - total_budget   # GP − Budget
            profit_after_actual = gross_profit - total_actual   # GP − Actual

            rec.bs_total_invoiced = total_invoiced
            rec.bs_total_project_cgs = cgs
            rec.bs_total_project_exp = opex
            rec.bs_total_project_exp_all = total_cost       # P3
            rec.bs_total_budget_cost = total_budget
            rec.bs_total_actual_cost = total_actual
            rec.bs_remaining_budget = total_budget - total_actual
            rec.bs_budget_variance = total_actual - total_budget
            rec.pp_gross_profit = gross_profit
            rec.pp_net_profit = net_profit
            rec.pp_budgeted_profit = profit_after_budget
            rec.pp_actual_profit = profit_after_actual

            _pct = self._kpi_pct
            rec.kpi_gross_margin = _pct(gross_profit, total_invoiced)
            rec.kpi_net_margin = _pct(net_profit, total_invoiced)
            rec.kpi_cogs_pct = _pct(cgs, total_invoiced)
            rec.kpi_opex_pct = _pct(opex, total_invoiced)
            rec.kpi_total_cost_pct = _pct(total_cost, total_invoiced)
            rec.kpi_roc = _pct(net_profit, total_cost)
            rec.kpi_budget_variance_pct = _pct(
                total_actual - total_budget, total_budget,
            )
            rec.kpi_budget_usage_pct = _pct(total_actual, total_budget)

    @api.depends(
        'commission_line_ids', 'commission_line_ids.amount',
        'commission_line_ids.state',
        'pp_actual_profit', 'bs_total_project_exp_all',
    )
    def _compute_commission_kpis(self):
        """Group 2 — commission total and everything derived from it.

        Kept separate from group 1 to break the dependency cycle with
        way4tech.manpower.commission.line._compute_amount (see the block
        comment above the field definitions).
        """
        for rec in self:
            commission_total = sum(
                l.amount or 0.0 for l in rec.commission_line_ids
                if l.state == 'billed'
            )
            # CR3-FINAL round 2, bug 1: base is Profit After Actual Cost
            # (client sheet F23 = F22 − B26), not Net Profit.
            after_commission = rec.pp_actual_profit - commission_total
            rec.bs_sales_person_commission = commission_total
            rec.pp_profit_after_commission = after_commission
            # CR3-FINAL P4 — follows the corrected base automatically.
            rec.kpi_net_return_on_cost_after_commission = self._kpi_pct(
                after_commission, rec.bs_total_project_exp_all,
            )

    # ══ CR3-FINAL P5: correct percentage aggregation at EVERY group level ══
    #
    # Odoo aggregates a stored Float measure with SUM. Summing percentages is
    # meaningless — two contracts at 89.65% and 40.00% are not a group at
    # 129.65% — and the client's rule is explicit: a percentage must be
    # recalculated at each level from that level's own summed amounts.
    #
    # This has to be done on BOTH group-read entry points. Odoo 19 has two,
    # and they do NOT share an implementation:
    #   • _read_group        — list-view group rollups, graph, direct ORM calls
    #   • _read_grouping_sets — what the PIVOT actually uses (via the JS
    #     `formattedReadGroupingSets`). It builds its own SQL GROUPING SETS
    #     query and never calls _read_group.
    # Overriding only _read_group leaves the pivot summing percentages while
    # every direct-ORM test passes — exactly the false pass that let this
    # ship. Both are patched below through one shared helper.

    def _way4tech_pct_plan(self, aggregates):
        """Work out which requested aggregates are KPI percentages.

        Returns (plan, extended_aggregates) where plan maps the position of a
        percentage aggregate to the positions of its numerator/denominator
        sums inside `extended_aggregates`. Returns (None, aggregates) when no
        percentage was asked for, so the caller can take the fast path.
        """
        plan = {}
        for index, spec in enumerate(aggregates):
            fname, _sep, func = spec.partition(':')
            if fname in self.PERCENT_MEASURES and func in ('sum', ''):
                num, den = self.PERCENT_MEASURES[fname]
                plan[index] = ('%s:sum' % num, '%s:sum' % den)
        if not plan:
            return None, aggregates
        extended = list(aggregates)
        for num_spec, den_spec in plan.values():
            for spec in (num_spec, den_spec):
                if spec not in extended:
                    extended.append(spec)
        return plan, tuple(extended)

    def _way4tech_pct_patch(self, rows, plan, extended, aggregates, n_groupby):
        """Substitute numerator ÷ denominator × 100 into each percentage cell
        and drop the helper columns we appended."""
        pos = {spec: n_groupby + i for i, spec in enumerate(extended)}
        keep = n_groupby + len(aggregates)
        patched = []
        for row in rows:
            row = list(row)
            for index, (num_spec, den_spec) in plan.items():
                numerator = row[pos[num_spec]] or 0.0
                denominator = row[pos[den_spec]] or 0.0
                row[n_groupby + index] = self._kpi_pct(numerator, denominator)
            patched.append(tuple(row[:keep]))
        return patched

    def _read_group(self, domain, groupby=(), aggregates=(), having=(),
                    offset=0, limit=None, order=None):
        """List-view rollups / graph / direct ORM calls."""
        plan, extended = self._way4tech_pct_plan(aggregates)
        if plan is None:
            return super()._read_group(
                domain, groupby, aggregates, having, offset, limit, order,
            )
        rows = super()._read_group(
            domain, groupby, extended, having, offset, limit, order,
        )
        return self._way4tech_pct_patch(
            rows, plan, extended, aggregates, len(groupby),
        )

    def _read_grouping_sets(self, domain, grouping_sets, aggregates=(),
                            order=None):
        """THE PIVOT PATH. Returns one result list per grouping set, so each
        has to be patched against its OWN groupby length — the grand-total
        set (groupby = ()) included, which is where the impossible 129.65%
        was showing up."""
        plan, extended = self._way4tech_pct_plan(aggregates)
        if plan is None:
            return super()._read_grouping_sets(
                domain, grouping_sets, aggregates, order,
            )
        results = super()._read_grouping_sets(
            domain, grouping_sets, extended, order,
        )
        return [
            self._way4tech_pct_patch(
                rows, plan, extended, aggregates, len(groupby),
            )
            for groupby, rows in zip(grouping_sets, results)
        ]

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
    )
    def _compute_invoice_count(self):
        """CR2 G5: posted-only. CR3-FINAL P1: Report Period scoping removed
        along with the header block — a monthly record IS the period."""
        for rec in self:
            rec.invoice_count = len(rec.invoice_ids)
            rec.total_invoiced = sum(
                inv.amount_untaxed for inv in rec.invoice_ids
                if inv.state == 'posted'
            )

    @api.depends('timesheet_ids.hours')
    def _compute_totals(self):
        for rec in self:
            rec.total_hours = sum(rec.timesheet_ids.mapped('hours'))
            rec.total_employee_cost = 0.0
            rec.billing_margin = 0.0

    @api.depends(
        'project_expense_ids.amount', 'project_expense_ids.state',
        'invoice_ids', 'invoice_ids.amount_untaxed', 'invoice_ids.state',
    )
    def _compute_project_margin(self):
        """CR2 G2 billed-only. CR3-FINAL P1: Report Period scoping removed.

        Depends on invoice_ids directly rather than on the non-stored
        total_invoiced — a stored field must not depend on a non-stored one
        or its invalidation becomes unreliable.
        """
        for rec in self:
            rec.total_project_expenses = sum(
                l.amount or 0.0 for l in rec.project_expense_ids
                if l.state == 'billed'
            )
            posted_invoiced = sum(
                inv.amount_untaxed for inv in rec.invoice_ids
                if inv.state == 'posted'
            )
            rec.project_margin = posted_invoiced - rec.total_project_expenses

    # ── CR3 P1 computes ────────────────────────────────────────────────────

    @api.depends('start_date')
    def _compute_contract_month(self):
        """CR3-FINAL P1: the record's month now derives from START DATE.

        Verified safe against live data before the re-key: on devnew there
        are zero (client, start-month, project) collisions among
        active/completed contracts, so populating contract_month from
        start_date cannot violate the partial unique index below.
        """
        for rec in self:
            # Guarded — rows with no start_date stay NULL (index skips them).
            rec.contract_month = (
                rec.start_date.replace(day=1) if rec.start_date else False
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
                    'one first, or pick a different Start Date, '
                    'Client, or Project.'
                ) % {'dup': dup.display_name or dup.reference or dup.id})

    # ── Reference auto-generation (P3) ──────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # --- CR3-FINAL P1/P8: start_date is the driver; mirror it back
            # onto the demoted accounting_date; auto-name from its month. ---
            # setdefault(start_date) BEFORE anything else so programmatic
            # callers like create({'client_id': X}) get a valid date instead
            # of hitting the downstream logic with None. Same value the UI
            # default (fields.Date.context_today) would supply.
            if not vals.get('start_date'):
                vals['start_date'] = fields.Date.context_today(self)
            # Mirror start_date -> accounting_date so the legacy readers that
            # still reference accounting_date (optional list column, search
            # filters, saved views) keep resolving. Reverse of the v12.0
            # direction: start_date now leads.
            if not vals.get('accounting_date'):
                vals['accounting_date'] = vals['start_date']
            # CR3-FINAL P8 auto-name: "Client — MM/YYYY" from the START DATE
            # month. Only when name is empty — records imported with a
            # pre-picked name are left alone (old records: display, never modify).
            if not vals.get('name') and vals.get('client_id') and vals.get('start_date'):
                client = self.env['res.partner'].browse(vals['client_id'])
                sd = fields.Date.to_date(vals['start_date'])
                if client and sd:
                    vals['name'] = '%s — %s' % (client.name, sd.strftime('%m/%Y'))
            # CR3-FINAL P1: the Due Date = Accounting Date + 45 days auto-fill
            # is REMOVED per client instruction. Nothing seeds due_date now.
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
        # CR3-FINAL P1: start_date leads — keep the demoted accounting_date
        # mirroring it so legacy filters/saved views stay consistent when the
        # user edits the header period. Only mirrors when the caller did not
        # explicitly set accounting_date in the same write.
        if vals.get('start_date') and 'accounting_date' not in vals:
            vals['accounting_date'] = vals['start_date']
        res = super().write(vals)
        # CR3-FINAL P8: backfill the auto-name for records still unnamed once
        # both ingredients exist (e.g. client picked after an initial save).
        # Never renames a record that already has a name — old records are
        # display-only.
        if {'client_id', 'start_date'} & set(vals):
            for rec in self:
                if not rec.name and rec.client_id and rec.start_date:
                    super(Way4TechManpowerContract, rec).write({
                        'name': '%s — %s' % (
                            rec.client_id.name, rec.start_date.strftime('%m/%Y'),
                        ),
                    })
        return res

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

    # ── CR3-FINAL Part A: per-item, consumed-once approval gate ───────────
    # Replaces the CR2 G5 (contract, month) gate. That one unlocked an entire
    # contract-month on a single approval, which is exactly what testing hit:
    # contract 36 was approved for 07/2026 once, and every document after it
    # went through unchallenged.
    #
    # The signature is kept for backwards compatibility with the ~40 existing
    # call sites, but target_date is now ignored — an approval is matched by
    # (model, record id), never by client, month or contract.
    def _require_month_approval(self, target_date=None, record=None):
        self.ensure_one()
        if record is None:
            # Contract-level actions (the legacy header Create Invoice) have
            # no specific row to point at. Under Part A every document must
            # come from a row, so refuse rather than silently allow.
            raise UserError(_(
                'Create the invoice from a Project Income invoice block '
                'instead. Contract-level invoicing is not approvable under '
                'the per-item approval rule, because there is no specific '
                'item for the approver to sign off.'
            ))
        return self.env['way4tech.manpower.approval.request']._require_approval(
            record,
        )

    def _consume_approval(self, record):
        self.ensure_one()
        return self.env['way4tech.manpower.approval.request']._consume_approval(
            record,
        )

    # ── Part A point 9: bulk request from the header ──────────────────────
    def _collect_pending_items(self):
        """Every draft row on this contract that could be sent for approval."""
        self.ensure_one()
        items = []
        for block in self.invoice_block_ids:
            if block.state == 'draft' and block.line_ids:
                items.append(block)
        for line in self.income_line_ids:
            if line.state == 'draft' and not line.invoice_block_id:
                items.append(line)
        for line in self.timesheet_ids:
            if line.state == 'draft':
                items.append(line)
        for line in self.project_expense_ids:
            if line.state == 'draft':
                items.append(line)
        for line in self.commission_line_ids:
            if line.state == 'draft':
                items.append(line)
        for line in self.budget_line_ids:
            if line.state == 'draft':
                items.append(line)
        return items

    def action_send_all_for_approval(self):
        """Send every current draft on this contract as ONE request."""
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_(
                'Activate the contract before sending items for approval.'
            ))
        items = self._collect_pending_items()
        if not items:
            raise UserError(_(
                'Nothing to send — every row on this contract is already '
                'approved, created or awaiting a decision.'
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send for Approval'),
            'res_model': 'way4tech.manpower.approval.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_contract_id': self.id,
                'default_mode': 'all',
            },
        }

    def action_view_approvals(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approvals'),
            'res_model': 'way4tech.manpower.approval.request',
            'view_mode': 'list,form',
            'domain': [('contract_id', '=', self.id)],
        }

    def action_send_for_signature(self):
        """Legacy entry point — now routes to the Part A approval wizard.

        Kept so any saved action, button or external reference still resolves.
        """
        self.ensure_one()
        return self.action_send_all_for_approval()

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

    # ── CR3-FINAL P11: Customer Statement → native Partner Ledger ─────────
    @api.depends('client_id', 'company_id')
    def _compute_client_balance(self):
        """Live outstanding balance for the contract's client.

        This is the SAME number the Partner Ledger prints as its closing
        balance: the signed sum (debit − credit) of every POSTED journal item
        on the partner's receivable AND payable accounts. Posted-only matches
        the Partner Ledger's own default, so the figure under the button and
        the figure at the bottom of the report always agree.

        Non-stored on purpose — it re-reads on every form open, so raising an
        invoice or registering a payment is reflected immediately with no
        recompute trigger to maintain. Aggregated in SQL via _read_group so
        it stays cheap on partners with thousands of entries.
        """
        for rec in self:
            if not rec.client_id:
                rec.client_balance = 0.0
                continue
            partner = rec.client_id | rec.client_id.commercial_partner_id
            groups = self.env['account.move.line']._read_group(
                domain=[
                    ('partner_id', 'in', partner.ids),
                    ('company_id', '=', rec.company_id.id),
                    ('account_id.account_type', 'in',
                     ('asset_receivable', 'liability_payable')),
                    ('parent_state', '=', 'posted'),
                ],
                aggregates=['balance:sum'],
            )
            rec.client_balance = (groups[0][0] if groups else 0.0) or 0.0

    def action_view_partner_ledger(self):
        """CR3-FINAL P11: open Odoo's NATIVE Partner Ledger for this client.

        Not a custom report — this is the standard Enterprise Partner Ledger
        (account_reports), so it carries the full ledger: receivable AND
        payable, every entry, with Journal / Account / Invoice Date / Due Date
        / Matching / Debit / Credit / running Balance columns and the native
        PDF and XLSX exports. It opens already filtered to this contract's
        client and unfolded, using the same mechanism Odoo itself uses for the
        partner form's statement buttons.

        Falls back to a partner-scoped journal-items list if account_reports
        is not installed, so the button never dead-ends on a Community
        database.
        """
        self.ensure_one()
        if not self.client_id:
            raise UserError(_(
                'Set a client on the contract before opening its statement.'
            ))
        partner = self.client_id | self.client_id.commercial_partner_id
        try:
            action = self.env['ir.actions.actions']._for_xml_id(
                'account_reports.action_account_report_partner_ledger',
            )
        except ValueError:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Partner Statement — %s') % self.client_id.display_name,
                'res_model': 'account.move.line',
                'view_mode': 'list,form',
                'domain': [
                    ('partner_id', 'in', partner.ids),
                    ('account_id.account_type', 'in',
                     ('asset_receivable', 'liability_payable')),
                ],
                'context': {'search_default_group_by_account': 1},
            }
        action['params'] = {
            'options': {
                'partner_ids': partner.ids,
                'unfold_all': True,
            },
            'ignore_session': True,
        }
        return action

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', self.invoice_ids.ids)],
        }

    # ── CR3-FINAL P7: one-click Print All Invoices ────────────────────────
    def action_print_all_invoices(self):
        """Render every invoice of this contract into ONE PDF file.

        Deliberately NOT merged into a single document: each invoice keeps
        its own page(s), its own sequence number, its own line table, its own
        VAT totals and its own ZATCA QR code. Passing the whole recordset to
        the KSA Tax Invoice report makes QWeb loop `docs` and start a fresh
        `<div class="page">` per invoice, which is precisely what ZATCA
        requires — one PDF, several separate tax invoices inside it.
        """
        self.ensure_one()
        invoices = self.invoice_ids.filtered(
            lambda m: m.move_type in ('out_invoice', 'out_refund')
            and m.state != 'cancel'
        ).sorted(lambda m: (m.invoice_date or m.date or fields.Date.today(), m.id))
        if not invoices:
            raise UserError(_(
                'This contract has no customer invoices to print yet. Create '
                'an invoice from the Project Income tab first.'
            ))
        report = self.env.ref(
            'way4tech_ksa_tax_invoice.action_report_ksa_tax_invoice',
            raise_if_not_found=False,
        )
        if not report:
            # KSA tax-invoice module not installed on this database — fall
            # back to Odoo's standard invoice report rather than failing.
            report = self.env.ref('account.account_invoices')
        return report.report_action(invoices)


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


