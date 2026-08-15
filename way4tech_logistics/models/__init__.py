# CR3-FINAL Part A: the approval mixin MUST be imported before any model that
# does `_inherit = ['way4tech.manpower.approval.mixin']`. Odoo resolves _inherit
# at class-registration time, so a later import gives
# "Model X inherits from non-existing model way4tech.manpower.approval.mixin".
from . import manpower_approval_request
# CR5 item 2: doc-line mixin (attachments + download) — same rule, import first.
from . import manpower_docline_mixin

from . import platform_config
from . import payroll_settings
from . import salary_import
from . import salary_import_line
from . import employee_ledger
from . import commission_receipt
from . import truck
from . import truck_trip
from . import employee_cost
from . import manpower_contract
from . import manpower_timesheet
from . import manpower_project_expense
from . import fleet_vehicle_extension
from . import vehicle_driver_assignment
from . import access_control
from . import fleet_service_extension
from . import partner_extension
from . import client_po
from . import equipment_rental
from . import equipment_rental_inbound
# ── New features (BRD v2) ────────────────────────────────────────────────────
from . import project
from . import tag
from . import entry_category
from . import installment_schedule
from . import asset_register
from . import account_move_extension
from . import account_move_line_extension
from . import account_move_sequence
from . import account_journal_ksa
from . import cashflow_alert
# 2026-07-15 — P3/P4/P5/P6/P7 additions
from . import expense_category
from . import settings_expense_account_map
from . import manpower_contract_income_line
from . import manpower_contract_budget_line
# 2026-07-17 — CR2 G3 Sales Person Commission (19.0.2.7.0)
from . import commission_template
from . import manpower_commission_line
# 2026-07-17 — CR2 G4 two-way sync + delete protection (19.0.2.8.0)
from . import account_move_sync
# 2026-07-17 — CR2 G5 monthly signature approval (19.0.2.9.0)
from . import manpower_contract_signature_request
# 2026-07-21 — CR3-FINAL P6 multi-line invoice blocks (19.0.3.1.0)
from . import manpower_invoice_block
# 2026-08 — Item 4: multi-line vendor bill blocks (mirror of invoice blocks)
from . import manpower_bill_block
# 2026-07-29 — CR6 item 1: multi-line timesheet invoice blocks (19.0.3.11.0)
from . import manpower_timesheet_block
# 2026-07-22 — CR3-FINAL round 2: date format + decimal precision (19.0.3.3.0)
from . import ksa_display_setup
# CR3-FINAL Part A approvals are imported at the TOP of this file — the mixin
# has to exist before the models that inherit it.
# 2026-07-24 — CR4 item 5: module-local product list
from . import manpower_product
# 2026-07-30 — CR7 item 1: read-only Project Expenses union (expense + commission).
# Imported LAST: its SQL VIEW references the project-expense, commission-line,
# contract and expense-category tables, which must all exist before init() runs.
from . import manpower_project_expense_report
# 2026-08-04 — CB1: Commissioning Business (config rules, settlement lines,
# invoice-selection wizard). commission_receipt (header) is imported above.
from . import commissioning_rules
from . import commission_settlement
from . import commission_invoice_select_wizard
