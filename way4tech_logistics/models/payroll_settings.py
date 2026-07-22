from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PayrollSettings(models.Model):
    """
    Central accounting configuration for Way4Tech Logistics.
    One record per company.  Admin fills in account codes ONCE and clicks
    "Apply to Salary Rules" — after that every payslip confirmation, every
    commission invoice and every vendor bill will use the right accounts.
    """
    _name = 'way4tech.payroll.settings'
    _description = 'Way4Tech Payroll & Accounting Settings'
    _rec_name = 'company_id'
    _check_company_auto = True

    _company_unique = models.Constraint(
        'UNIQUE(company_id)',
        'Only one settings record per company is allowed.',
    )

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        ondelete='cascade',
    )

    # ── Payroll ───────────────────────────────────────────────────────────────
    payroll_journal_id = fields.Many2one(
        'account.journal',
        string='Payroll Journal',
        check_company=True,
        domain=[('type', '=', 'general')],
        help='Journal used when payslips are confirmed and journal entries are created.',
    )

    # Earnings — Expense side (Debit on payslip confirmation)
    salary_expense_account_id = fields.Many2one(
        'account.account',
        string='Salary Expense Account',
        check_company=True,
        help='Basic salary + order adjustment earnings.\n'
             'Dr this account when payslip is confirmed.',
    )
    bonus_expense_account_id = fields.Many2one(
        'account.account',
        string='Bonus Expense Account',
        check_company=True,
        help='Bonus line on payslip.  Falls back to Salary Expense if not set.',
    )
    petrol_expense_account_id = fields.Many2one(
        'account.account',
        string='Petrol Allowance Account',
        check_company=True,
        help='Petrol allowance line.  Falls back to Salary Expense if not set.',
    )

    # Salary Payable — Liability side (Credit on payslip confirmation)
    salary_payable_account_id = fields.Many2one(
        'account.account',
        string='Salary Payable Account',
        check_company=True,
        help='Liability account credited when payslip is confirmed.\n'
             'Debited when salaries are paid to employees.',
    )

    # Performance deductions — deduction contra account
    perf_deduction_account_id = fields.Many2one(
        'account.account',
        string='Performance Deductions Account',
        check_company=True,
        help='On-time, food damage, miss-day, order rejection, misc deductions.\n'
             'With negative payslip amount, Dr Salary Payable — Cr this account.',
    )

    # Office/ledger deductions — each clears its own balance
    advance_account_id = fields.Many2one(
        'account.account',
        string='Employee Advances Account',
        check_company=True,
        help='Asset account for advances given to employees.\n'
             'Advance given: Dr this, Cr Bank.\n'
             'Advance recovered in salary: Dr Salary Payable, Cr this.',
    )
    loan_account_id = fields.Many2one(
        'account.account',
        string='Employee Loans Account',
        check_company=True,
        help='Asset account for loans given to employees.',
    )
    fuel_deduction_account_id = fields.Many2one(
        'account.account',
        string='Fuel Deduction Account',
        check_company=True,
        help='Account credited when fuel is deducted from salary.',
    )
    sim_deduction_account_id = fields.Many2one(
        'account.account',
        string='SIM Charges Account',
        check_company=True,
        help='Account credited when SIM charges are deducted from salary.',
    )
    traffic_deduction_account_id = fields.Many2one(
        'account.account',
        string='Traffic Violation Account',
        check_company=True,
        help='Account credited when traffic fines are deducted from salary.',
    )
    rent_deduction_account_id = fields.Many2one(
        'account.account',
        string='Rent Deduction Account',
        check_company=True,
        help='Account credited when rent is deducted from salary.',
    )

    # ── Commission ────────────────────────────────────────────────────────────
    commission_income_account_id = fields.Many2one(
        'account.account',
        string='Commission Income Account',
        check_company=True,
        help='Income account on commission invoices raised to customers.',
    )
    commission_journal_id = fields.Many2one(
        'account.journal',
        string='Commission Sales Journal',
        check_company=True,
        domain=[('type', '=', 'sale')],
        help='Journal used when creating commission invoices.',
    )
    subcontractor_expense_account_id = fields.Many2one(
        'account.account',
        string='Subcontractor Payable Account (Expense)',
        check_company=True,
        help='Expense account on the vendor bill created for the subcontractor\'s share.',
    )

    # ── Trucks / Fleet ────────────────────────────────────────────────────────
    truck_revenue_account_id = fields.Many2one(
        'account.account',
        string='Truck Revenue Account',
        check_company=True,
        help='Income account for truck trip revenue.',
    )
    truck_expense_account_id = fields.Many2one(
        'account.account',
        string='Truck Expense Account',
        check_company=True,
        help='Expense account for truck maintenance, fuel and other costs.',
    )
    investor_payable_account_id = fields.Many2one(
        'account.account',
        string='Investor Profit Share Account',
        check_company=True,
        help='Expense account on vendor bills created for investor profit share payouts.',
    )
    truck_trip_journal_id = fields.Many2one(
        'account.journal',
        string='Truck Trip Sales Journal',
        check_company=True,
        domain=[('type', '=', 'sale')],
        help='Sales journal for truck trip customer invoices.',
    )
    truck_costs_payable_account_id = fields.Many2one(
        'account.account',
        string='Truck Trip Costs Payable Account',
        check_company=True,
        help='Liability account credited when trip operational costs (fuel, driver, other) '
             'are posted as a journal entry.\n'
             'Example: "2150 - Truck Costs Payable" or "2100 - Accrued Expenses".\n'
             'Debited when you actually pay the fuel supplier / driver.',
    )
    truck_expense_journal_id = fields.Many2one(
        'account.journal',
        string='Truck Expense Journal',
        check_company=True,
        domain=[('type', 'in', ['general', 'purchase'])],
        help='Journal type: General or Purchase. Used for truck trip operational cost '
             'journal entries (fuel, driver, other costs). '
             'Leave blank to fall back to the Employee Compliance Journal.',
    )
    installment_payable_account_id = fields.Many2one(
        'account.account',
        string='Installment Payable Account',
        check_company=True,
        help='Liability account for vehicle installment financing.\n'
             'Saudi accounting: Long-term or Current Liability (account_type: liability_non_current '
             'or liability_current).\n'
             'Example: 220010 – Installment Payable / 220020 – Vehicle Financing Payable.\n'
             'Debited when monthly installment is paid (Dr this Cr Bank). '
             'Credited when vehicle is purchased on installment (Dr Fixed Asset Cr this).',
    )
    rental_income_account_id = fields.Many2one(
        'account.account',
        string='Equipment Rental Income Account',
        check_company=True,
        help='Income account credited on equipment / machinery rental invoices.\n'
             'Example: 500010 – Equipment Rental Income (income type).\n'
             'Falls back to Truck Revenue Account if not set.',
    )
    rental_journal_id = fields.Many2one(
        'account.journal',
        string='Equipment Rental Sales Journal',
        check_company=True,
        domain=[('type', '=', 'sale')],
        help='Sales journal used when creating customer invoices for equipment rentals.\n'
             'Falls back to Truck Trip Sales Journal if not set.',
    )

    rental_expense_account_id = fields.Many2one(
        'account.account',
        string='Equipment Rental Expense Account',
        check_company=True,
        help='Expense account debited on vendor bills for equipment rented FROM vendors.\n'
             'Example: 600020 – Equipment Rental Expense.\n'
             'Falls back to Truck Expense Account if not set.',
    )
    rental_expense_journal_id = fields.Many2one(
        'account.journal',
        string='Equipment Rental Purchase Journal',
        check_company=True,
        domain=[('type', '=', 'purchase')],
        help='Purchase journal for vendor bills of rented equipment.\n'
             'Falls back to Truck Expense Journal if not set.',
    )

    # ── Manpower ──────────────────────────────────────────────────────────────
    manpower_income_account_id = fields.Many2one(
        'account.account',
        string='Manpower Income Account',
        check_company=True,
        help='Income account on manpower contract customer invoices.',
    )
    manpower_journal_id = fields.Many2one(
        'account.journal',
        string='Manpower Sales Journal',
        check_company=True,
        domain=[('type', '=', 'sale')],
        help='Sales journal for manpower contract invoices.',
    )

    # ── Project Expenses (Construction / Project-Based Manpower) ─────────────
    project_wages_account_id = fields.Many2one(
        'account.account',
        string='Worker Wages Account',
        check_company=True,
        help='Expense account debited when a "Worker Wages" project expense vendor bill is created.\n'
             'Example: 5200 — Project Labour Cost.',
    )
    project_accommodation_account_id = fields.Many2one(
        'account.account',
        string='Accommodation Expense Account',
        check_company=True,
        help='Expense account debited for accommodation costs billed to a project.\n'
             'Example: 5210 — Accommodation & Housing.',
    )
    project_utilities_account_id = fields.Many2one(
        'account.account',
        string='Utilities Expense Account',
        check_company=True,
        help='Expense account debited for utilities (electricity, water, internet) on a project.\n'
             'Example: 5220 — Project Utilities.',
    )
    project_furniture_account_id = fields.Many2one(
        'account.account',
        string='Furniture & Equipment Account',
        check_company=True,
        help='Expense account debited for furniture and equipment costs on a project.\n'
             'Example: 5230 — Project Equipment & Supplies.',
    )
    project_transport_account_id = fields.Many2one(
        'account.account',
        string='Transport Expense Account',
        check_company=True,
        help='Expense account debited for transport and mobilisation costs on a project.\n'
             'Example: 5240 — Project Transport.',
    )
    project_other_expense_account_id = fields.Many2one(
        'account.account',
        string='Other Project Expense Account',
        check_company=True,
        help='Expense account debited for miscellaneous project costs not covered by '
             'the specific types above.\n'
             'Example: 5290 — Other Project Expenses.',
    )
    # ── CR3-FINAL Part A point 6: who approves ────────────────────────────
    manpower_approver_id = fields.Many2one(
        'res.users', string='Approver',
        help='The authorised user who approves manpower documents. Every '
             '"Send for Approval" routes here automatically — the requester '
             'never picks a signer. Nobody may approve their own request, so '
             'keep this as someone other than the day-to-day accountant.',
    )
    # NOTE: a Many2one to sign.template would make this module hard-depend on
    # the Enterprise `sign` app, which contradicts its Community packaging.
    # The Sign hand-off is therefore left late-bound (see
    # way4tech.manpower.approval.request._launch_sign_request, which no-ops
    # when no template is configured). Wiring it up properly needs a decision
    # on taking the Enterprise dependency.

    # ── P4/P5/P7 (2026-07-15): per-business-division accounts referenced
    #    by the Manpower Contract Income + Expense tabs. Kept nullable so
    #    the settings screen stays valid on existing tenants until an
    #    accountant fills them in.
    manpower_receivable_account_id = fields.Many2one(
        'account.account', string='Manpower Receivable Account', check_company=True,
        help='140001 Direct Business Receivable (or the equivalent for this '
             'business division). Set on invoices generated from the Project '
             'Income tab so accounts-receivable posts to the correct GL.',
    )
    manpower_vat_output_account_id = fields.Many2one(
        'account.account', string='Manpower Output VAT Account', check_company=True,
        help='250000 Output VAT — used by the Project Income tab. Optional; '
             'if left empty, invoices fall back to the tax record default.',
    )
    manpower_payable_account_id = fields.Many2one(
        'account.account', string='Manpower Payable Account', check_company=True,
        help='210001 Manpower Payable — credited on vendor bills generated '
             'from the Project Expenses tab. Kept separate per business division.',
    )
    manpower_expense_category_account_ids = fields.One2many(
        'way4tech.settings.expense.account.map', 'settings_id',
        string='Expense Category → GL Account Map',
        help='Per-category GL expense account. Selecting a category on a '
             'Project Expense line auto-fills the account from this map.',
    )
    project_expense_journal_id = fields.Many2one(
        'account.journal',
        string='Project Expense Journal',
        check_company=True,
        domain=[('type', '=', 'purchase')],
        help='Purchase journal used for vendor bills created from project expense lines '
             '(wages, accommodation, utilities, furniture, transport, other).\n'
             'Leave blank to use the default purchase journal.',
    )

    # ── CR2 G3 (19.0.2.7.0) — Sales Person Commission Rules ───────────────
    commission_expense_account_id = fields.Many2one(
        'account.account',
        string='Sales Person Commission Expense Account',
        check_company=True,
        help='GL expense account debited on the vendor bill created from a '
             'Sales Person Commission line on a Manpower Contract.\n'
             'Example: 620010 — Sales Commission Expense (Operating Exp).',
    )
    commission_template_ids = fields.One2many(
        'way4tech.commission.template', 'settings_id',
        string='Sales Person Commission Rules',
        help='Per-employee commission rate table. One row per salesperson '
             'per company. Referenced by manpower.contract._get_commission_amount() '
             "to look up the rate for the picked commission_type on each contract.",
    )

    # ── Employee Compliance Costs (KSA) ───────────────────────────────────────
    gosi_expense_account_id = fields.Many2one(
        'account.account',
        string='GOSI Expense Account',
        check_company=True,
        help='Expense account debited for employer GOSI contributions.',
    )
    iqama_expense_account_id = fields.Many2one(
        'account.account',
        string='Iqama/Residency Expense Account',
        check_company=True,
        help='Expense account debited for Iqama renewal and residency costs.',
    )
    insurance_expense_account_id = fields.Many2one(
        'account.account',
        string='Medical Insurance Expense Account',
        check_company=True,
        help='Expense account debited for employee medical insurance.',
    )
    saudization_expense_account_id = fields.Many2one(
        'account.account',
        string='Saudization (Nitaqat) Expense Account',
        check_company=True,
        help='Expense account debited for Saudization/Nitaqat fees.',
    )
    other_compliance_account_id = fields.Many2one(
        'account.account',
        string='Other Compliance Expense Account',
        check_company=True,
        help='Expense account debited for miscellaneous employee compliance costs '
             '(Other Costs field on Employee Cost record).',
    )
    compliance_payable_account_id = fields.Many2one(
        'account.account',
        string='Compliance Costs Payable Account',
        check_company=True,
        help='Liability account credited when GOSI, Iqama, Insurance or Saudization costs are posted.',
    )
    employee_cost_journal_id = fields.Many2one(
        'account.journal',
        string='Employee Compliance Journal',
        check_company=True,
        domain=[('type', 'in', ['general', 'purchase'])],
        help='Journal used for employee compliance cost journal entries (GOSI, Iqama, etc.).',
    )

    # ── Analytics ─────────────────────────────────────────────────────────────
    default_analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Default Analytic Account',
        help='Applied to payroll, commission, and fleet entries when no specific '
             'analytic is set on the individual record.',
    )

    # ── Methods ───────────────────────────────────────────────────────────────

    @api.model
    def get_for_company(self, company_id=None):
        """Return the settings record for the given (or current) company."""
        company_id = company_id or self.env.company.id
        settings = self.search([('company_id', '=', company_id)], limit=1)
        if not settings:
            settings = self.create({'company_id': company_id})
        return settings

    @api.model
    def action_open_for_company(self):
        """Open the settings record for the current company (creates one if missing).
        Used as the menu action so the user always lands on the existing record,
        never on a blank new-record form that would hit the unique constraint."""
        settings = self.get_for_company()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payroll & Accounting Setup'),
            'res_model': 'way4tech.payroll.settings',
            'res_id': settings.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_auto_detect_accounts(self):
        """
        Full account + journal setup for KSA companies.

        Strategy per field (only fills EMPTY fields — never overwrites):
          1. Search by KSA account code (works when l10n_sa chart is installed)
          2. Search by account_type + Arabic/English name keyword
          3. CREATE the account with the standard KSA code & name if still not found

        Journals are detected only (not created) — they are set up during
        Accounting module installation.

        KSA account codes reference (l10n_sa / l10n_sa_hr_payroll):
          106012  Prepaid Employee Expenses   (asset_current)
          201002  Salaries Payable            (liability_payable)
          201016  Accrued Expenses            (liability_current)
          201022  GOSI & Compliance Payable   (liability_current)
          201098  Investor Profit Payable     (liability_current)  — Way4Tech
          201099  Truck Costs Payable         (liability_current)  — Way4Tech
          400003  Basic Salary                (expense)
          400005  Transportation Allowance    (expense)
          400009  Medical Insurance           (expense)
          400010  GOSI Employer Contribution  (expense)
          400012  Staff Other Allowances      (expense)
          400014  Visa & Iqama Expenses       (expense)
          400048  Vehicle & Fleet Expenses    (expense)           — Way4Tech
          400074  Salary Deductions           (expense)
          500003  Commission Income           (income)            — Way4Tech
          500008  Transport Revenue           (income)            — Way4Tech
          500009  Manpower Income             (income)            — Way4Tech
        """
        self.ensure_one()
        Account = self.env['account.account']
        Journal = self.env['account.journal']
        company_id = self.company_id.id
        company_domain = [('company_ids', 'in', [company_id])]

        detected = []
        created = []

        def _by_code(code):
            return Account.search(company_domain + [('code', '=', code)], limit=1)

        def _by_type(*args):
            """_by_type(account_type, hint1, hint2, ...) — search by type then names."""
            account_type = args[0]
            hints = args[1:]
            base = company_domain + [('account_type', '=', account_type)]
            for hint in hints:
                r = Account.search(base + [('name', 'ilike', hint)], limit=1)
                if r:
                    return r
            return Account.search(base, limit=1)

        def _get_or_create(code, name, account_type, *hints):
            """Return (account, 'detected'|'created'). Never overwrites existing."""
            acc = _by_code(code)
            if acc:
                return acc, 'detected'
            acc = _by_type(account_type, *hints)
            if acc:
                return acc, 'detected'
            # Create with standard KSA code
            acc = Account.create({
                'code': code,
                'name': name,
                'account_type': account_type,
                'company_ids': [company_id],
            })
            return acc, 'created'

        def _set(field, code, name, account_type, *hints):
            if getattr(self, field):
                return  # already set — never overwrite
            acc, mode = _get_or_create(code, name, account_type, *hints)
            updates[field] = acc.id
            (created if mode == 'created' else detected).append('%s (%s)' % (acc.name, acc.code))

        def _journal(field, jtype, *hints):
            if getattr(self, field):
                return
            base = [('type', '=', jtype), ('company_id', '=', company_id)]
            for hint in hints:
                j = Journal.search(base + [('name', 'ilike', hint)], limit=1)
                if j:
                    updates[field] = j.id
                    detected.append('Journal: %s' % j.name)
                    return
            j = Journal.search(base, limit=1)
            if j:
                updates[field] = j.id
                detected.append('Journal: %s' % j.name)

        updates = {}

        # ── PAYROLL — earnings ───────────────────────────────────────────────
        _set('salary_expense_account_id',  '400003', 'Basic Salary',               'expense',           'salary', 'wage', 'basic')
        _set('bonus_expense_account_id',   '400012', 'Staff Other Allowances',     'expense',           'bonus', 'allowance', 'other allow')
        _set('petrol_expense_account_id',  '400005', 'Transportation Allowance',   'expense',           'petrol', 'transport allow', 'fuel allow')

        # ── PAYROLL — payable ────────────────────────────────────────────────
        _set('salary_payable_account_id',  '201002', 'Salaries Payable',           'liability_payable', 'salaries payable', 'salary payable', 'payroll payable')

        # ── PAYROLL — deductions ─────────────────────────────────────────────
        _set('perf_deduction_account_id',  '400074', 'Salary Deductions',          'expense',           'deduction', 'salary deduct', 'penalty')
        _set('fuel_deduction_account_id',  '400074', 'Salary Deductions',          'expense',           'deduction', 'fuel deduct')
        _set('sim_deduction_account_id',   '400074', 'Salary Deductions',          'expense',           'deduction', 'sim', 'communication deduct')
        _set('traffic_deduction_account_id','400074','Salary Deductions',          'expense',           'deduction', 'traffic', 'fine')
        _set('rent_deduction_account_id',  '400074', 'Salary Deductions',          'expense',           'deduction', 'rent')

        # ── PAYROLL — advance / loan asset ───────────────────────────────────
        _set('advance_account_id',         '106012', 'Prepaid Employee Expenses',  'asset_current',     'advance', 'prepaid employee', 'staff advance')
        _set('loan_account_id',            '106012', 'Prepaid Employee Expenses',  'asset_current',     'loan', 'employee loan', 'advance')

        # ── COMMISSION ───────────────────────────────────────────────────────
        _set('commission_income_account_id',  '500003', 'Commission Income',       'income',            'commission income', 'commission', 'service income')
        _set('subcontractor_expense_account_id','400003','Basic Salary',           'expense',           'subcontractor', 'freelancer', 'labour')

        # ── FLEET / TRUCKS ───────────────────────────────────────────────────
        _set('truck_revenue_account_id',   '500008', 'Transport Revenue',          'income',            'transport revenue', 'fleet income', 'vehicle income')
        _set('truck_expense_account_id',   '400048', 'Vehicle & Fleet Expenses',   'expense',           'vehicle', 'fleet expense', 'truck expense')
        _set('truck_costs_payable_account_id', '201099', 'Truck Costs Payable',    'liability_current', 'truck costs payable', 'accrued trip', 'fleet payable')
        _set('investor_payable_account_id','201098', 'Investor Profit Payable',    'liability_current', 'investor', 'profit payable', 'investor payable')
        _set('installment_payable_account_id', '220010', 'Installment Payable',    'liability_non_current', 'installment payable', 'vehicle financing', 'hire purchase')
        _set('rental_income_account_id',      '500010', 'Equipment Rental Income', 'income',                'equipment rental', 'machinery rental', 'rental income')

        # ── MANPOWER ─────────────────────────────────────────────────────────
        # Al Zain / KSA convention: 410001 = Direct Business Sale (main
        # manpower revenue). Keywords also match "direct business" so the
        # scan lands the correct row on tenants that have it.
        _set('manpower_income_account_id',       '410001', 'Direct Business Sale',        'income',              'direct business sale', 'direct business', 'manpower income', 'manpower', 'labour income')
        _set('manpower_receivable_account_id',   '140001', 'Direct Business Receivable',  'asset_receivable',    'direct business receivable', 'direct business', 'manpower receivable')
        _set('manpower_vat_output_account_id',   '250000', 'Output VAT',                  'liability_current',   'output vat', 'vat output', 'sales vat')
        _set('manpower_payable_account_id',      '210001', 'Manpower Payable',            'liability_current',   'manpower payable', 'labour payable', 'direct business payable')

        # ── KSA COMPLIANCE ───────────────────────────────────────────────────
        _set('gosi_expense_account_id',       '400010', 'GOSI Employer Contribution', 'expense',         'gosi', 'social insurance employer', 'life insurance')
        _set('iqama_expense_account_id',      '400014', 'Visa & Iqama Expenses',      'expense',         'iqama', 'visa expense', 'residency')
        _set('insurance_expense_account_id',  '400009', 'Medical Insurance',          'expense',         'medical insurance', 'health insurance', 'insurance')
        _set('saudization_expense_account_id','400012', 'Staff Other Allowances',     'expense',         'saudization', 'nitaqat', 'quota')
        _set('other_compliance_account_id',  '400019', 'Other Staff Expenses',        'expense',         'other staff expense', 'other compliance', 'miscellaneous staff')
        _set('compliance_payable_account_id', '201022', 'GOSI & Compliance Payable',  'liability_current','gosi payable', 'compliance payable', 'social insurance payable')

        # ── JOURNALS ─────────────────────────────────────────────────────────
        _journal('payroll_journal_id',        'general',  'payroll', 'salary', 'miscellaneous')
        _journal('commission_journal_id',     'sale',     'customer', 'sales', 'invoice')
        _journal('truck_trip_journal_id',     'sale',     'customer', 'sales', 'invoice')
        _journal('manpower_journal_id',       'sale',     'customer', 'sales', 'invoice')
        _journal('truck_expense_journal_id',  'general',  'miscellaneous', 'general', 'payroll')
        _journal('employee_cost_journal_id',  'general',  'payroll', 'miscellaneous', 'general')
        _journal('rental_journal_id',         'sale',     'customer', 'sales', 'invoice')

        if updates:
            self.write(updates)

        # ── Summary notification ─────────────────────────────────────────────
        total = len(detected) + len(created)
        lines = []
        if detected:
            lines.append(_('%d fields filled from existing accounts/journals.') % len(detected))
        if created:
            lines.append(_('%d new KSA accounts created: %s') % (
                len(created), ', '.join(created[:6]) + ('…' if len(created) > 6 else '')
            ))
        if not updates:
            lines.append(_('All fields are already filled — nothing to update.'))

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Account Setup Complete (%d fields)') % total,
                'message': '\n'.join(lines),
                'type': 'success' if updates and not created else ('info' if not created else 'warning'),
                'sticky': True,
            },
        }
