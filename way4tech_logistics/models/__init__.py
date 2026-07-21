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
