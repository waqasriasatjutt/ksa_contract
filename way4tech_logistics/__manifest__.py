{
    'name': 'Way4Tech Logistics & HR Extensions',
    'version': '19.0.4.1.21',
    'summary': 'Complete operations management for KSA logistics & manpower companies — payroll, fleet, manpower contracts, investor P&L, and full accounting integration for Odoo 19',
    'description': '''
Way4Tech Logistics & HR Extensions
====================================
Complete Operations Management for KSA Logistics & Manpower Companies
Odoo 19 Enterprise | Saudi Arabia (KSA) | Multi-Company

REQUIRES ODOO ENTERPRISE — the manpower approval workflow signs through the
Enterprise Sign app (module `sign`), and the Customer/Partner Statement opens
the Enterprise Partner Ledger (`account_reports`) when it is installed.

PURPOSE
-------
One module that covers the entire operational and accounting cycle for logistics and
manpower companies operating in the Kingdom of Saudi Arabia (Alzain Towers /
Woodpecker Logistics model). Eliminates the need for separate payroll, fleet, HR, and
finance modules by providing a tightly integrated, purpose-built solution.

────────────────────────────────────────────────────────────────
KEY MODULES & FEATURES
────────────────────────────────────────────────────────────────

1. PAYROLL & ACCOUNTING SETUP  (Configuration → Payroll & Accounting Setup)
   ─────────────────────────────────────────────────────────────────────────
   Central one-record-per-company configuration screen. Maps every GL account and
   journal used across all 9 financial operations. Tabs cover:
     • Payroll — salary expense, bonus, petrol, payable, deductions
     • Commission — income account, sales journal, subcontractor payable
     • Fleet & Trucks — revenue, expense, investor share, installment payable
     • Manpower Contracts — income account, sales journal, project expense accounts
     • Employee Compliance (KSA) — GOSI, Iqama, insurance, Saudization payables
     • Analytics — company-wide default analytic account
   Auto-Detect Accounts button scans your chart of accounts by keyword to prefill fields.

2. PLATFORM CONFIGURATION  (Configuration → Platform Configurations)
   ──────────────────────────────────────────────────────────────────
   Salary formula engine for delivery platforms (HungerStation, Keeta, Chefz, etc.).
     • Fixed salary when worker meets minimum working days (default: 27 days)
     • Per-order rate applied when below minimum days
     • Order adjustment: short-order deduction per trip below target; excess-order bonus
     • Petrol allowance per order
   Used automatically when computing salary in the Worker Salary Import.

3. WORKER SALARY IMPORT  (Payroll → Salary Imports)
   ──────────────────────────────────────────────────
   Excel-based bulk payroll for delivery riders and workers.
     • Download template, fill 20 columns per worker (days, orders, all earnings/deductions)
     • Upload Excel → lines created, salary auto-computed from platform rules
     • Fill from Ledger: pulls outstanding advance/deduction balances and pre-fills recovery
     • Compute All: recalculates every line in one click
     • Mark Imported: locks lines; transitions to Imported state
     • Post to Accounting: creates a single journal entry (Dr Salary Expense / Cr Salary Payable)
       for the entire batch — one debit line per earnings component, one credit per deduction type
     • Mark Deductions Recovered: marks linked ledger records as recovered
   PDF Report: full salary sheet with totals, colour-coded error rows.

4. EMPLOYEE ADVANCES & DEDUCTIONS  (hidden by default — enable via menu_views.xml)
   ──────────────────────────────────────────────────────────────────────────────────
   Tracks every financial obligation per employee (advance, fuel, SIM, loan, traffic
   fine, rent deduction). Each record posts a journal entry immediately on save.
   Outstanding Balances view shows total charged vs. recovered per employee — used by
   "Fill from Ledger" in salary import to auto-populate recovery amounts.

5. COMMISSION RECEIPTS  (Commission → Commission Receipts)
   ─────────────────────────────────────────────────────────
   Manages commission invoicing with KSA 15% VAT handling.
     • VAT-correct formula: Net Amount × commission % = company share (ex-VAT)
     • Creates Customer Invoice (out_invoice) for the full amount to subcontractor
     • Creates Vendor Bill (in_invoice) for subcontractor's net share
   PDF Report: itemised commission breakdown statement.

6. FLEET & TRUCKS  (Fleet & Trucks menu)
   ────────────────────────────────────────
   a) Truck Management (Trucks)
      • Company-owned and investor-owned trucks — separate profit-share logic per ownership
      • Vehicle categories, purchase value, fixed asset account
      • Installment financing: total price, down payment, monthly amount, first date,
        paid count, total count, outstanding balance, estimated payoff date
      • PO limit per trip enforcement — blocks trip creation if PO would be exceeded
      • Operational status: Active / Under Maintenance / Inactive — auto-toggled by maintenance
      • Smart buttons: Trip count, P&L records, direct navigation

   b) Trips  (Fleet & Trucks → Trips)
      • Rental types: Daily / Hourly / Per Trip / Monthly / Project
      • Revenue: auto-calculated from type + rate
      • Costs: driver basic + overtime + food allowance + fuel + other
      • Gross Profit = Revenue − Total Cost
      • Salesperson tracking per trip
      • Create Invoice: one-click customer invoice at configured revenue account
      • Create Cost Entry: journal entry for driver cost at configured cost accounts

   c) Investor P&L  (Truck → P&L Records smart button)
      • Period P&L: total revenue, expenses, gross profit
      • Profit share split at configured % (e.g. 50/50 with investor)
      • Indirect expenses: yard rent, coordinator salary, Iqama, other operational
      • Company Net = Company Gross − Indirect Expenses
      • Auto-create investor vendor bill; mark as paid with payment date

   d) Maintenance  (Fleet & Trucks → Maintenance)
      • Inherits fleet.vehicle.log.services with Way4Tech extensions
      • Categories: Preventive / Corrective / Accident Repair / Tyres / Other
      • Workflow: Draft → Confirmed → Done (auto-toggles truck operational status)
      • Create Vendor Bill at configured truck expense account
      • Analytic distribution on all bill lines

   e) Client POs  (Fleet & Trucks → Client POs)
      • Tracks purchase orders per client with total value and per-trip limit
      • Remaining balance computed automatically from linked trips
      • Auto-renewal action

   f) Profitability Reports  (Fleet & Trucks → Profitability Reports)
      • Date range + trip status filter + optional truck/client filter
      • Truck-wise: one page per truck, revenue/cost/profit/margin%; grand total summary
      • Customer-wise: same layout grouped by client

   g) Investor Aging Report  (Fleet & Trucks → Investor Aging Report)
      • Outstanding investor payable balances grouped by truck and aging buckets

   h) Maintenance History Report  (Fleet & Trucks → Maintenance History Report)
      • Date range + optional truck filter + category filter
      • Per-truck detail table: reference, date, category, state, vendor, cost
      • Repeated-category alert: highlights maintenance types that recur > once in period

7. MANPOWER CONTRACTS  (Manpower menu)
   ─────────────────────────────────────
   a) Contracts  (Manpower → Manpower Contracts)
      • Contract types: Food Delivery (riders/supervisors) or Project-Based
      • Billing types: Fixed Price (monthly) or Hourly Rate (total hours × rate)
      • Salesperson assigned per contract — used in Salesperson Profitability Report
      • Assigned Manpower tab: employees, roles, start/end, daily cost (internal reference)
      • Timesheets tab: daily hours log per employee — drives Hourly Rate invoicing
      • Project Expenses tab (Project-Based only): wages, accommodation, utilities,
        furniture, transport, other — each line can create a vendor bill
      • Project Margin = Total Invoiced − Total Project Expenses
      • Analytic account on all invoice and bill lines
      • Create Invoice: one-click invoice at configured manpower income account + 15% VAT
   PDF Report: full contract statement, assigned manpower, timesheet log, notes.

   b) Project Expenses  (Manpower → Project Expenses)
      • Standalone view of all project cost lines across contracts

   c) Salesperson Profitability Report  (Manpower → Salesperson Profitability Report)
      • Date range + optional salesperson filter
      • Per salesperson: truck trips (revenue/cost/profit/margin%) + manpower contracts
        (invoiced/expenses/margin)
      • Summary table + detailed drill-down per salesperson

8. EMPLOYEE KSA COMPLIANCE COSTS  (hidden by default)
   ──────────────────────────────────────────────────────
   Tracks statutory employer costs per employee for KSA compliance:
     • GOSI (default 11.75% employer share, auto-calculated from basic salary)
     • Iqama / Residency renewal
     • Medical Insurance
     • Saudization / Nitaqat levy
     • Other compliance expenses
   Post Expenses creates a multi-line journal entry (Dr each expense / Cr compliance payable).

────────────────────────────────────────────────────────────────
ACCOUNTING INTEGRATION
────────────────────────────────────────────────────────────────
Every financial operation produces a standard Odoo account.move document:

  Operation                        Document Type
  ─────────────────────────────    ──────────────────────────────────────
  Worker Salary Batch              Journal Entry (Dr Expense / Cr Payable)
  Employee Advance / Deduction     Journal Entry (Dr/Cr at posting)
  KSA Compliance Costs             Journal Entry (Dr Expense / Cr Payable)
  Commission Receipt               Customer Invoice (out_invoice)
  Commission Subcontractor Share   Vendor Bill (in_invoice)
  Truck Trip                       Customer Invoice (out_invoice)
  Truck Trip Driver Cost           Journal Entry (Dr Cost / Cr Payable)
  Investor Profit Share            Vendor Bill (in_invoice)
  Maintenance Service              Vendor Bill (in_invoice)
  Manpower Contract Invoice        Customer Invoice (out_invoice) + 15% VAT
  Manpower Project Expense         Vendor Bill (in_invoice)

Analytic distribution is applied to every journal line from the document's
analytic account, falling back to the company default in Payroll & Accounting Setup.

────────────────────────────────────────────────────────────────
PDF REPORTS
────────────────────────────────────────────────────────────────
  • Worker Salary Sheet (per import batch)
  • Commission Receipt Statement
  • Investor Profit Statement (per P&L record)
  • Investor Aging Report (wizard — date range, aging buckets)
  • Truck-wise Profitability Report (wizard — date range, truck filter)
  • Customer-wise Profitability Report (wizard — date range, client filter)
  • Maintenance History Report (wizard — date range, truck/category filter, repeat alerts)
  • Manpower Contract Statement (timesheets, assigned staff, expenses)
  • Salesperson Profitability Report (wizard — trips + contracts by salesperson)

────────────────────────────────────────────────────────────────
SECURITY
────────────────────────────────────────────────────────────────
  Logistics User    — read access on all records; can log deductions; run Excel import
  Logistics Manager — full CRUD, posting actions, invoice creation, configuration

────────────────────────────────────────────────────────────────
DEPENDENCIES
────────────────────────────────────────────────────────────────
  Edition      : Odoo 19 ENTERPRISE (required — see below)
  Odoo modules : account, analytic, mail, fleet, hr, sign
                 (`sign` is an Enterprise app — it powers the manpower
                  approval / signature workflow)
  Enterprise   : `sign` (hard dependency); `account_reports` used at runtime
                 for the Partner Ledger when present (falls back gracefully)
  Python libs  : openpyxl   (Excel import/export)
                 xlsxwriter (Cumulative Statement XLSX export)
''',
    'category': 'Human Resources/Payroll',
    'author': 'Waqas Riasat',
    'maintainer': 'Way4Tech',
    'website': 'https://way4tech.com',
    'license': 'OPL-1',
    'price': 30.0,
    'currency': 'USD',
    'support': 'support@way4tech.com',
    'images': ['static/description/banner.svg'],
    'depends': [
        'account',
        'analytic',
        'mail',
        'fleet',
        'hr',
        # CR3-FINAL round 3, item 8 — client confirmed the Enterprise
        # dependency. Manpower approvals are signed in Odoo Sign, which is what
        # produces the signed PDF, the signer record and the audit trail.
        # NOTE: this makes the module Enterprise-only from 19.0.3.6.0 onward.
        'sign',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'data/cron_data.xml',
        'data/category_data.xml',
        'data/expense_category_data.xml',
        'data/manpower_pro_sequence_data.xml',
        'data/ksa_sequence_setup.xml',
        # CR3-FINAL round 2: dates d/m/y + 2-decimal precision
        'data/ksa_display_setup.xml',
        # CR6 item 2: Product Price precision -> 6 dp (exact invoice amounts)
        'data/decimal_precision_data.xml',
        # ── Wizard views ──────────────────────────────────────────────────────
        'wizard/salary_excel_import_views.xml',
        'wizard/fleet_excel_export_views.xml',
        'wizard/maintenance_excel_wizard_views.xml',
        'wizard/truck_profitability_wizard_views.xml',
        'wizard/investor_aging_wizard_views.xml',
        'wizard/setup_wizard_views.xml',
        'wizard/rejection_wizard_views.xml',
        'wizard/employee_category_report_wizard_views.xml',
        'wizard/staff_cost_report_wizard_views.xml',
        'wizard/employee_margin_report_wizard_views.xml',
        # CR3-FINAL P12: Send for Signature popup
        'wizard/manpower_signature_wizard_views.xml',
        # CR4 item 7: zero-amount bill confirmation dialog
        'wizard/manpower_zero_bill_wizard_views.xml',
        # ── Model views ───────────────────────────────────────────────────────
        'views/report_salesperson_profitability.xml',
        'views/report_maintenance_history.xml',
        # CR5 item 11: Expense Category page MUST load before payroll_settings —
        # the Manpower tab there has a button referencing action_expense_category.
        'views/expense_category_views.xml',
        'views/payroll_settings_views.xml',
        'views/platform_config_views.xml',
        'views/salary_import_views.xml',
        'views/commission_receipt_views.xml',
        'views/commission_settlement_views.xml',
        'views/commission_invoice_select_wizard_views.xml',
        'views/client_po_views.xml',
        'views/truck_views.xml',
        'views/vehicle_driver_assignment_views.xml',
        'views/truck_trip_views.xml',
        'views/truck_maintenance_views.xml',
        'views/employee_cost_views.xml',
        'views/manpower_contract_views.xml',
        'views/manpower_project_expense_views.xml',
        # CR5 item 2a: per-line "Files & Document" dialogs (attachments upload +
        # single-document download). Additive; opened by the paperclip button.
        'views/manpower_docline_attach_views.xml',
        # CR2 G5 (19.0.2.9.0): monthly signature approval workflow
        'views/manpower_contract_signature_request_views.xml',
        # CR3-FINAL Part A: per-item, consumed-once approvals
        'views/manpower_approval_views.xml',
        'views/employee_ledger_views.xml',
        'views/partner_employee_views.xml',
        # ── New BRD v2 views ──────────────────────────────────────────────────
        'views/entry_category_views.xml',
        'views/asset_register_views.xml',
        'views/installment_schedule_views.xml',
        'views/cashflow_alert_views.xml',
        'views/account_move_category_views.xml',
        'views/account_move_line_dimensions_views.xml',
        'views/account_move_invoice_vehicle_views.xml',
        'views/account_move_filter_extensions_views.xml',
        'views/way4tech_dimensions_views.xml',
        'views/equipment_rental_views.xml',
        'views/equipment_rental_inbound_views.xml',
        # ── Reports ───────────────────────────────────────────────────────────
        'views/report_commission_receipt.xml',
        'views/report_investor_payable.xml',
        'views/report_salary_import.xml',
        'views/report_manpower_contract.xml',
        # CR2 G5 (19.0.2.9.0): draft-snapshot statement PDF
        'views/report_manpower_contract_statement.xml',
        # CR3-FINAL Part D: cumulative multi-month statement
        'views/report_manpower_cumulative.xml',
        'views/report_truck_profitability.xml',
        'views/report_investor_aging.xml',
        'views/report_employee_category.xml',
        'views/report_staff_cost.xml',
        'views/report_employee_margin.xml',
        'views/report_fleet_data.xml',
        # ── Menu (always last) ────────────────────────────────────────────────
        'views/menu_views.xml',
    ],
    'application': True,
    'installable': True,
}
