# Project Tracking — Alzain Towers / Woodpecker Logistics
**Module:** `way4tech_logistics`
**Client:** Alzain Tower Contracting Est + Woodpecker Logistics + Future Power Trading + Fame Island Contracting + Mehar Areen Facility Contracting
**Odoo Version:** 19.0 (Community)
**Vendor:** Way4Tech
**Document Purpose:** Single source of truth for requirements history, billing, implementation status, and change tracking. Used by both the Way4Tech team and the AI assistant when new requirements arrive so nothing gets mis-quoted or missed.

---

## How to use this document

1. **When a new BRD / feedback arrives** → add a new row in Section 2 (Change Log) and a new version column in Section 3 (Requirement Matrix). Mark each item as `new`, `already-covered`, `minor-mod`, or `future`.
2. **Before sending a quote** → check Section 4 (Implementation Status) to verify what's already built vs what needs new work. Bill only for work not already covered.
3. **During implementation** → update Section 4 statuses as features land.
4. **For future compare with AI** → share this file + the new requirements doc, and ask: *"compare this new doc against this tracking file and give me only the truly new items."*

---

## Section 1 — Project Timeline

| Date | Event | Version | Amount (SAR) |
|---|---|---|---|
| 2026-01-15 | BRD v1.0 received from client (first document) | BRD-v1 | — |
| 2026-01-xx | Quotation sent to client | Quote-v1 | **3,700** |
| 2026-xx-xx | Quote accepted, project kickoff | — | — |
| 2026-03-xx | BRD v2 received (expanded scope) | BRD-v2 | — |
| 2026-03-xx | Change Request #1 quoted for 7 new items | CR-1 | **3,500** |
| 2026-04-xx | BRD v3 received (further expanded scope + 2 future items) | BRD-v3 | — |
| 2026-04-15 | Change Request #2 quoted for 17 new items | CR-2 | **8,500** |
| — | **Revised Total Project Cost** | — | **15,700** |

---

## Section 2 — Change Log

### BRD v1 (2026-01-15) — Original Scope

**Key points from first BRD:**
- Multi-branch company setup (1 parent + 3 branches: Woodpecker, Future Power, Fame Island)
- Transportation & fleet: own trucks + investor trucks + trip/rental usage tracking + maintenance logs + investor payable
- PO limit check against rental revenue per truck (from first BRD §4.2)
- Manpower: food delivery riders (own + freelancer), project-based manpower, timesheet-driven invoicing
- Commission invoicing (5% after VAT)
- Profitability dimensions: Branch / Customer / Project / Truck / Investor
- Reports: P&L, customer profitability, investor aging, employee cost, VAT, cash statement
- Role-based access per company and department (generic)

**Quotation v1 — SAR 3,700 (delivered):**
- Phase 1 (standard config): Multi-company, VAT, manpower records, fleet cost tracking, investor payable tracking
- Phase 2 (custom dev): Rider payroll Excel import, commission invoicing module, branch/customer/project profitability reports

### BRD v2 (March 2026) — First Expansion

**Delta from BRD v1 — 7 new items quoted as CR-1 (SAR 3,500):**

| # | Item | Why it's new |
|---|---|---|
| 1 | Installment Bus Tracking (2 units) | Not in v1 |
| 2 | Indirect Expense Layer (yard rent + coordinator + iqama + other) with Net Profit formula | Not in v1 |
| 3 | Detailed truck revenue formulas (Hours+OT / Per-Trip / Flatbed Fixed) | v1 was vague |
| 4 | Invoice/bill scan attachments + ZIP bundle with reports | Not in v1 |
| 5 | Inventory for fleet parts (spare, tires, oil, batteries) + repeat detection | Not in v1 |
| 6 | PO 80-90% alert + renewal workflow (basic PO check was in v1) | Only alert+renewal new |
| 7 | Salesperson-wise profitability | Not in v1's 5 dimensions |

### BRD v3 (April 2026) — Second Expansion

**Delta from BRD v2 — 17 new items quoted as CR-2 (SAR 8,500):**

**A. New Business Lines (5)**
1. Middleman truck rental (3rd-party hire → client)
2. Yard rental income (sub-rental to another party)
3. Equipment/machinery rental TO clients (outbound)
4. Equipment/machinery rental FROM vendors (inbound — generators etc.)
5. Two additional Main CRs (Fame Island + Mehar Areen)

**B. Accounting Controls (4)**
6. Mandatory Entry Category System on all account moves
7. Invoice Category with mandatory admin-controlled selection
8. Approval workflow for journal entries > 500 SAR
9. Selective bill-level access restriction

**C. Automation & Alerts (3)**
10. Daily/weekly/monthly cash flow alerts to owner via WhatsApp/Email with graph
11. Employee category-wise report with auto-send (email/WhatsApp)
12. Direct email/WhatsApp sending for invoices/reports

**D. UX Features (2)**
13. Previous expense display feature (historical context on new entries)
14. Graph/chart view on ALL reports

**E. Asset Management (1)**
15. Asset Depreciation & Residual Value Management (SL / DB methods)

**F. New Reports (2)**
16. Office Staff Cost Breakdown (salary + SIM + car + fuel + FAT + iqama + insurance + GOSI + Saudization)
17. Rider/Driver Ledger + Profit Margin (Employee Margin = Revenue − Cost)

**Future Phase (explicitly deferred in BRD v3 "Extra/later on"):**
- Purchase Invoice OCR Scanner Integration
- Mobile Thumb Attendance + Geofencing

---

## Section 3 — Full Requirement Matrix

Legend: ✅ Implemented • 🟡 Partial • ⏳ Pending • 🔵 New (future) • ❌ Excluded

### Fleet & Truck

| Requirement | BRD-v1 | BRD-v2 | BRD-v3 | In Quote | Status | Module File(s) |
|---|---|---|---|---|---|---|
| Fleet vehicle with own/investor/sponsored/sold ownership | ✓ | ✓ | ✓ | v1 | ✅ | `fleet_vehicle_extension.py` |
| Investor partner link + profit share % | ✓ | ✓ | ✓ | v1 | ✅ | `fleet_vehicle_extension.py` |
| Truck chassis #, plate type, sequence # | | ✓ | ✓ | CR-1 | ✅ | `fleet_vehicle_extension.py` |
| Registration/inspection/insurance/operation card expiry + 60-day cron | | ✓ | ✓ | CR-1 | ✅ | `fleet_vehicle_extension.py` |
| Driver assignment with iqama, handover/return dates | | ✓ | ✓ | CR-1 | ✅ | `vehicle_driver_assignment.py` |
| **Installment bus tracking** (2 units) + monthly schedule + payoff | | ✓ | ✓ | CR-1 | ✅ | `installment_schedule.py` |
| Installment payment via vendor bill (not raw JE) | | | | — | ✅ extra | `installment_schedule.py::action_pay` |
| Trip model: delivery/rental/flatbed/middleman/yard_rental | ✓ | ✓ | ✓ | v1+CR-1+CR-2 | ✅ | `truck_trip.py` |
| **Middleman 3rd-party cost line** (conditional on trip_type) | | | ✓ | CR-2 | ✅ | `truck_trip.py` |
| **Yard rental income** as trip_type | | | ✓ | CR-2 | ✅ | `truck_trip.py` |
| Revenue basis: manual/hours/per_trip/flat | | ✓ | ✓ | CR-1 | ✅ | `truck_trip.py::rental_type` |
| Driver cost breakdown (basic+OT+food) | | ✓ | ✓ | CR-1 | ✅ | `truck_trip.py` |
| Auto-select current driver when truck chosen | | | ✓ | CR-2 | ✅ | `truck_trip.py::_onchange_truck_autoselect_driver` |
| License plate on trip list view | | | ✓ | CR-2 | ✅ | `truck_trip_views.xml` |
| Multi-project allocation on flat-rate trips | | | ✓ | CR-2 | ✅ | `truck_trip.py::Way4TechTripProjectAllocation` |
| PO balance tracking (basic limit check) | ✓ | ✓ | ✓ | v1 | ✅ | `client_po.py` |
| PO 80-90% alert + renewal workflow | | ✓ | ✓ | CR-1 | 🟡 (alert done, renewal pending) | `client_po.py::_notify_near_limit` |
| PO balance uses actual invoice amount (not trip revenue) | | | | — | ✅ extra | `client_po.py::_compute_balance` |
| **PO per-category rates** (car/truck/helper hourly) | | | ✓ | CR-2 | ⏳ | — |

### Maintenance

| Requirement | BRD-v1 | BRD-v2 | BRD-v3 | In Quote | Status | Module File(s) |
|---|---|---|---|---|---|---|
| Maintenance logs per vehicle | ✓ | ✓ | ✓ | v1 | ✅ | `fleet_service_extension.py` |
| Create vendor bill from maintenance | ✓ | ✓ | ✓ | v1 | ✅ | `fleet_service_extension.py::action_create_bill` |
| Maintenance history report | ✓ | ✓ | ✓ | v1 | ✅ | `wizard/maintenance_history_wizard.py` |
| **Repeated repair detection** (same category within window) | | ✓ | ✓ | CR-1 | 🟡 (report shows categories, detection logic pending) | `wizard/maintenance_history_wizard.py` |
| **Attach scan copy to maintenance bill** | | ✓ | ✓ | CR-1 | 🟡 (chatter allows, no dedicated field) | `fleet_service_extension.py` |
| **Inventory for fleet parts** (tires, oil, batteries) | | ✓ | ✓ | CR-1 | ⏳ | — |
| **Excel import/export for maintenance** | | ✓ | ✓ | CR-1 | ⏳ | — |

### Investor Payable / Fleet Profitability

| Requirement | BRD-v1 | BRD-v2 | BRD-v3 | In Quote | Status | Module File(s) |
|---|---|---|---|---|---|---|
| Investor payable model | ✓ | ✓ | ✓ | v1 | ✅ | `truck.py::Way4TechInvestorPayable` |
| Monthly/yearly profit share | ✓ | ✓ | ✓ | v1 | ✅ | `truck.py::_compute_amounts` |
| 50/50 split + investor bears no indirect | | ✓ | ✓ | CR-1 | ✅ | `truck.py::_compute_amounts` |
| **Indirect expense layer** (yard rent + coordinator + iqama + other) | | ✓ | ✓ | CR-1 | ✅ | `truck.py` |
| Gross & Net profit formulas | | ✓ | ✓ | CR-1 | ✅ | `truck.py::_compute_amounts` |
| Investor bill as `in_invoice` | | | | — | ✅ extra | `truck.py::action_create_bill` |
| Auto-compute from trips + maintenance | ✓ | ✓ | ✓ | v1 | ✅ | `truck.py::action_compute_from_trips` |
| Hide company-owned truck fields (investor %, amount) | | | | — | ✅ extra | `truck_views.xml` |
| License plate in profitability report/list | | | ✓ | CR-2 | ✅ | `truck.py::truck_license_plate`, `truck_views.xml` |
| **Investor share basis: Gross OR Net option** | | | ✓ | CR-2 | ✅ | `truck.py::investor_share_basis` |
| Cron filters investor-only trucks (not company-owned) | | | | — | ✅ extra | `truck.py::_auto_generate_monthly_payables` |
| Investor aging report | ✓ | ✓ | ✓ | v1 | ✅ | `wizard/investor_aging_wizard.py` |

### Manpower / Riders / Employees

| Requirement | BRD-v1 | BRD-v2 | BRD-v3 | In Quote | Status | Module File(s) |
|---|---|---|---|---|---|---|
| Employee records for own staff + vendor for freelancers | ✓ | ✓ | ✓ | v1 | ✅ | core + `partner_extension.py` |
| Rider payroll Excel import | ✓ | ✓ | ✓ | v1 | ✅ | `salary_import.py`, `wizard/salary_excel_import.py` |
| Platform config (HungerStation/Keeta/Chefz rules) | ✓ | ✓ | ✓ | v1 | ✅ | `platform_config.py` |
| Compute Net = Earnings − Deductions | ✓ | ✓ | ✓ | v1 | ✅ | `salary_import_line.py` |
| Post salary batch as journal entry | ✓ | ✓ | ✓ | v1 | ✅ | `salary_import.py::action_post_to_accounting` |
| Employee compliance costs (GOSI/iqama/insurance/Saudization) | ✓ | ✓ | ✓ | v1 | ✅ | `employee_cost.py` |
| Employee deduction ledger (advance/loan/fine) | ✓ | ✓ | ✓ | v1 | ✅ | `employee_ledger.py` |
| **Driver payroll components** (basic/OT/food/loan/advance/fine) | | ✓ | ✓ | CR-1 | 🟡 (via salary_import) | `salary_import_line.py` |
| **Driver Iqama on employee** | | | ✓ | CR-2 | ✅ | `partner_extension.py::HrEmployee` |
| **Partner CR# (company) / Iqama# (individual)** | | | ✓ | CR-2 | ✅ | `partner_extension.py::ResPartner` |
| Manpower contracts with fixed/hourly billing | ✓ | ✓ | ✓ | v1 | ✅ | `manpower_contract.py` |
| Project expense tracking | ✓ | ✓ | ✓ | v1 | ✅ | `manpower_project_expense.py` |

### Commission Invoicing

| Requirement | BRD-v1 | BRD-v2 | BRD-v3 | In Quote | Status | Module File(s) |
|---|---|---|---|---|---|---|
| Commission receipt (5% after VAT) | ✓ | ✓ | ✓ | v1 | ✅ | `commission_receipt.py` |
| Customer invoice to subcontractor | ✓ | ✓ | ✓ | v1 | ✅ | `commission_receipt.py::action_create_commission_invoice` |
| Vendor bill for subcontractor payable | ✓ | ✓ | ✓ | v1 | ✅ | `commission_receipt.py::action_create_subcontractor_bill` |
| Commission reports (daily/monthly/yearly) | ✓ | ✓ | ✓ | v1 | ✅ | `report_commission_receipt.xml` |

### Equipment Rental

| Requirement | BRD-v1 | BRD-v2 | BRD-v3 | In Quote | Status | Module File(s) |
|---|---|---|---|---|---|---|
| **Equipment rental to clients (outbound)** | | | ✓ | CR-2 | ✅ | `equipment_rental.py` |
| Rate types: daily/weekly/monthly/fixed | | | | — | ✅ extra | `equipment_rental.py` |
| Rate types: hourly + basic+hourly | | | ✓ | CR-2 | ✅ | `equipment_rental.py` |
| **Equipment rental from vendors (inbound)** | | | ✓ | CR-2 | 🟡 (model exists, review vs BRD-v3 §6) | `equipment_rental_inbound.py` |

### Accounting Controls

| Requirement | BRD-v1 | BRD-v2 | BRD-v3 | In Quote | Status | Module File(s) |
|---|---|---|---|---|---|---|
| VAT 15% KSA (quarterly) | ✓ | ✓ | ✓ | v1 | ✅ | standard Odoo + `l10n_sa` |
| Role-based access (generic) | ✓ | ✓ | ✓ | v1 | ✅ | `security/security.xml`, `access_control.py` |
| **Restrict back-date entries** | | ✓ | ✓ | CR-1 | 🟡 (access_control.py has hooks) | `access_control.py` |
| **Restrict delete transactions** | | ✓ | ✓ | CR-1 | ✅ | `security.xml` (no unlink for users) |
| **Restrict ledger creation** | | ✓ | ✓ | CR-1 | 🟡 | `access_control.py` |
| **Restrict vendor creation** | | ✓ | ✓ | CR-1 | 🟡 | `access_control.py` |
| **Restrict P&L report access** | | ✓ | ✓ | CR-1 | ✅ | `security.xml` |
| **Mandatory Entry Category on all moves** | | | ✓ | CR-2 | ✅ | `entry_category.py`, `account_move_extension.py` |
| **Invoice Category with mandatory selection** | | | ✓ | CR-2 | 🟡 (entry category works for moves; dedicated invoice category admin-control pending) | `entry_category.py` |
| **Approval workflow > 500 SAR** | | | ✓ | CR-2 | ✅ | `account_move_extension.py::action_post` |
| **Rejection wizard with reason** | | | ✓ | CR-2 | ✅ | `wizard/rejection_wizard.py` |
| **Selective bill-level restriction** | | | ✓ | CR-2 | ⏳ | — |

### Reports

| Requirement | BRD-v1 | BRD-v2 | BRD-v3 | In Quote | Status | Module File(s) |
|---|---|---|---|---|---|---|
| Truck-wise profitability | ✓ | ✓ | ✓ | v1 | ✅ | `wizard/truck_profitability_wizard.py` |
| Customer-wise profitability | ✓ | ✓ | ✓ | v1 | ✅ | `wizard/truck_profitability_wizard.py` |
| Salesperson profitability | | ✓ | ✓ | CR-1 | ✅ | `wizard/salesperson_profitability_wizard.py` |
| Investor aging | ✓ | ✓ | ✓ | v1 | ✅ | `wizard/investor_aging_wizard.py` |
| Receivable/payable aging | ✓ | ✓ | ✓ | v1 | 🟡 (use standard Odoo) | standard |
| Maintenance history report | ✓ | ✓ | ✓ | v1 | ✅ | `wizard/maintenance_history_wizard.py` |
| Employee margin report | | ✓ | ✓ | CR-1 | ✅ | `wizard/employee_margin_report_wizard.py` |
| Employee category-wise report | | | ✓ | CR-2 | ✅ | `wizard/employee_category_report_wizard.py` |
| **Employee category report auto-send (email/WhatsApp)** | | | ✓ | CR-2 | ⏳ | — |
| Staff cost report | | ✓ | ✓ | CR-1 | ✅ | `wizard/staff_cost_report_wizard.py` |
| **Office Staff Cost Breakdown** (SIM+car+fuel+FAT+...) | | | ✓ | CR-2 | 🟡 (base report exists, extra fields pending) | `wizard/staff_cost_report_wizard.py` |
| **Rider/Driver Ledger + Profit Margin** | | | ✓ | CR-2 | ✅ (margin) | `wizard/employee_margin_report_wizard.py` |
| **Graph/chart view on ALL reports** | | | ✓ | CR-2 | ⏳ | — |

### Automation & Alerts

| Requirement | BRD-v1 | BRD-v2 | BRD-v3 | In Quote | Status | Module File(s) |
|---|---|---|---|---|---|---|
| Fleet expiry cron (60-day warning) | | ✓ | ✓ | CR-1 | ✅ | `fleet_vehicle_extension.py::_cron_fleet_expiry_notifications` |
| Investor payable auto-generate monthly cron | ✓ | ✓ | ✓ | v1 | ✅ | `truck.py::_auto_generate_monthly_payables` |
| Installment due reminder cron | | ✓ | ✓ | CR-1 | ✅ | `installment_schedule.py::_cron_send_due_reminders` |
| **Cashflow alert config** | | | ✓ | CR-2 | 🟡 (model exists, WhatsApp/email send pending) | `cashflow_alert.py` |
| **Daily cashflow alert to owner's mobile with graph** | | | ✓ | CR-2 | ⏳ | — |
| **Email/WhatsApp direct send** | | | ✓ | CR-2 | ⏳ | — |

### Data Import / Attachments

| Requirement | BRD-v1 | BRD-v2 | BRD-v3 | In Quote | Status | Module File(s) |
|---|---|---|---|---|---|---|
| Rider payroll Excel import | ✓ | ✓ | ✓ | v1 | ✅ | `wizard/salary_excel_import.py` |
| **Excel import for driver salary + advances + fuel + iqama** | | ✓ | ✓ | CR-1 | 🟡 (template covers riders; driver extension pending) | `wizard/salary_excel_import.py` |
| **Excel import for fleet master data** | | | ✓ | CR-2 | ⏳ | — |
| **Excel import for trips** | | | ✓ | CR-2 | ⏳ | — |
| **Bill scan attachments on expenses** | | ✓ | ✓ | CR-1 | 🟡 (chatter allows attachments; dedicated attachment field pending) | — |
| **ZIP bundle report with related invoices** | | ✓ | ✓ | CR-1 | ⏳ | — |

### UX Features

| Requirement | BRD-v1 | BRD-v2 | BRD-v3 | In Quote | Status | Module File(s) |
|---|---|---|---|---|---|---|
| **Previous expense display on new entry** | | | ✓ | CR-2 | 🟡 (account_move_extension has `way4tech_prev_expense` field, display pending) | `account_move_extension.py` |
| **Asset depreciation (SL/DB + residual)** | | | ✓ | CR-2 | 🟡 (asset_register.py exists, depreciation compute partial) | `asset_register.py` |

### Future Phase (explicitly deferred — NOT in any quote)

| Requirement | Source | Status |
|---|---|---|
| Purchase Invoice OCR Scanner | BRD-v3 | 🔵 future quote |
| Mobile Thumb Attendance + Geofencing | BRD-v3 | 🔵 future quote |

---

## Section 4 — Implementation Status Summary

### ✅ Fully implemented (25+ major areas)

1. Multi-company setup (5 companies)
2. Fleet vehicle with full KSA identifiers (chassis, plate, sequence)
3. Investor/own/sponsored/sold ownership + profit share
4. Expiry tracking + 60-day notification cron (4 document types)
5. Driver assignment with iqama tracking
6. Installment bus tracking with vendor bill flow
7. Trip model with 6 types including middleman + yard rental
8. Trip revenue basis (manual/hours/per-trip/flat)
9. Multi-project allocation on flat-rate trips
10. Fleet Profitability with gross/net profit formulas + investor share basis option
11. Indirect expense layer (yard rent + coordinator + iqama + other)
12. Maintenance logs with vendor bill creation
13. Rider payroll Excel import with platform rules
14. Commission invoicing (5% after VAT) with customer invoice + vendor bill flow
15. Client PO with balance tracking + near-limit notification
16. Employee compliance cost tracking (GOSI/iqama/insurance/Saudization)
17. Employee deduction ledger (advance/loan/fine)
18. Equipment rental (outbound) with all rate types
19. Mandatory entry category on journal entries
20. Approval workflow > 500 SAR with rejection wizard
21. Reports: truck profitability, salesperson profitability, investor aging, maintenance history, employee margin, employee category, staff cost
22. **Fleet identification** (chassis, plate type, sequence — Session 4)
23. **Expiry tracking** (registration, inspection, insurance, operation card + 60-day cron)
24. **Driver assignment** with iqama, handover/return tracking
25. **Fleet PDF Report** (Session 4)
26. **Fleet Excel Export** (Session 4)
27. **Maintenance Excel Import + Export** (Session 4)
28. **Maintenance scan copy attachment field** (Session 4)
29. **Partner CR/Iqama + Employee Iqama** notebook tabs (Session 4)
30. **Multi-project allocation on trips** (for Flat Rate only)
31. **Vehicle Models admin menu + extended vehicle types** (Session 4)
32. **Investor share basis selector** (Gross vs Net)

### 🟡 Partial — needs completion

1. **Driver salary components** in salary_import (currently rider-focused)
2. **Repeated repair detection** in maintenance history report (logic missing)
3. **Attach scan copy field** on maintenance bill (uses chatter only)
4. **PO renewal workflow** (alert done, renewal action pending)
5. **Invoice category with admin-per-user control** (entry category works for moves only)
6. **Selective bill-level restriction** (not yet implemented)
7. **Cashflow alert WhatsApp/email send** (config exists, delivery pending)
8. **Bill scan attachment** dedicated field on expenses
9. **Previous expense display** widget (field exists, UI pending)
10. **Asset depreciation compute** (model exists, SL/DB logic pending)
11. **Office staff cost breakdown** (SIM/car/fuel/FAT fields pending)

### ⏳ Pending — not started

1. **Inventory for fleet parts** (tires, oil, batteries as stock)
2. **Excel import for fleet master data** (export DONE 2026-04-16)
3. **Excel import/export for trips**
4. ~~Excel import/export for maintenance~~ ✅ **Done 2026-04-16** (both import and export)
5. **ZIP bundle report with related invoices**
6. **PO per-category rates** (car/truck/helper hourly)
7. **Daily cashflow alerts to owner** with graph via WhatsApp/Email
8. **Employee category report auto-send** (email/WhatsApp)
9. **Email/WhatsApp direct-send** for invoices/reports
10. **Graph/chart view on ALL reports**
11. **PO renewal workflow** (80% alert + renewal button/wizard)
12. **Repeated repair detection** in maintenance history report
13. **Previous expense display widget** (field exists, UI pending)
14. **Asset depreciation compute** (SL/DB methods)
15. **Office staff cost breakdown fields** (SIM/car/fuel/FAT)
16. **Invoice category admin control per user**
17. **Bill-level access restriction**

### 🎁 Extra features added beyond any quote (free value for client)

These are features we built that were NOT in any BRD or quote — value-add that strengthens the deliverable but should be noted for future negotiations:

1. **Vendor bill flow for installment payments** (proper Odoo accounting vs raw JE)
2. **Investor bill as `in_invoice`** with full payment reconciliation
3. **PO balance uses actual posted invoice amount** (not trip revenue field)
4. **Hide investor fields on company-owned profitability** (UX polish)
5. **Cron filters investor-only trucks** for monthly auto-generate (BRD v1 implied all)
6. **License plate auto-sync** across trip + profitability list views
7. **Entry category auto-assignment** block in `action_post` if categories exist but none selected (mandatory gate)
8. **Way4Tech sequence number + fleet sequence generator**
9. **View binding fixes** (custom forms for `fleet.vehicle` and `fleet.vehicle.log.services` — Odoo was showing built-in forms)
10. **Maintenance smart button points to custom action** (was pointing to core `fleet.fleet_vehicle_log_services_action`)

### 🔵 Future / Not quoted

- Purchase Invoice OCR Scanner Integration
- Mobile Thumb Attendance + Geofencing

---

## Section 5 — Billing Summary (as of BRD v3)

| Phase | Description | Amount (SAR) |
|---|---|---|
| Quote v1 | First BRD scope — Phase 1 (config) + Phase 2 (rider payroll + commission + reports) | 3,700 |
| CR #1 | 7 items from BRD v2 (installment, indirect layer, scan attach, inventory, repeat detect, PO alert+renewal, salesperson) | 3,500 |
| CR #2 | 17 items from BRD v3 (business lines + accounting controls + automation + UX + depreciation + reports) | 8,500 |
| **Revised Total** | | **15,700** |

### Payment Schedule (proposed)

| Milestone | % | Amount |
|---|---|---|
| On Quote-v1 confirmation | 50% of 3,700 | 1,850 |
| On CR-1 approval | 50% of 3,500 | 1,750 |
| On UAT / custom module delivery | 30% of 3,700 | 1,110 |
| On CR-2 approval | 50% of 8,500 | 4,250 |
| On CR-1 delivery | 50% of 3,500 | 1,750 |
| On CR-2 delivery | 50% of 8,500 | 4,250 |
| On final deployment | 20% of 3,700 | 740 |
| **Total** | | **15,700** |

### Exclusions (unchanged across all versions)

- Odoo Enterprise licenses
- Full KSA HR payroll legal compliance (beyond basic GOSI/Saudization tracking)
- Mobile applications / third-party API integrations beyond WhatsApp/Email for alerts
- Hosting / server management
- AMC / support contracts beyond 15-day post-deployment
- Purchase Invoice OCR Scanner (BRD-v3 Extra §1)
- Mobile Thumb Attendance + Geofencing (BRD-v3 Extra §2)

---

## Section 6 — Priority Roadmap for Remaining Work

### Sprint 1 (Week 1-2) — CR-1 remaining

- [ ] Repeated repair detection logic in maintenance history report
- [ ] Attach scan field + inventory for fleet parts (tires/oil/batteries as stock)
- [ ] Bill scan attachments on expense entries
- [ ] ZIP bundle report with related invoices
- [ ] PO renewal workflow (add value to PO or create linked new PO)
- [ ] Driver salary Excel import extension

### Sprint 2 (Week 3-4) — CR-2 Phase A

- [ ] Vendor equipment rental (inbound) model verification against BRD-v3 §6
- [ ] PO per-category rates (car/truck/helper hourly)
- [ ] Excel import/export: fleet master data + trips + maintenance
- [ ] Invoice category admin-control per user
- [ ] Selective bill-level restriction

### Sprint 3 (Week 5) — CR-2 Phase B

- [ ] Daily cashflow alert scheduler + graph generation
- [ ] Email template + WhatsApp API integration
- [ ] Employee category report auto-send
- [ ] Direct invoice/report send via email/WhatsApp

### Sprint 4 (Week 6) — CR-2 Phase C

- [ ] Previous expense display widget
- [ ] Asset depreciation SL/DB compute logic
- [ ] Office staff cost breakdown (SIM/car/fuel/FAT fields)
- [ ] Graph/chart view added to all existing reports

### Future (separate quote)

- [ ] Purchase Invoice OCR Scanner
- [ ] Mobile Thumb Attendance + Geofencing

---

## Section 7 — How to Handle New Requirement Changes

When the client sends another updated BRD or feedback:

### Step 1: Log it

Add a new row to **Section 1 — Project Timeline** and a new entry in **Section 2 — Change Log**.

### Step 2: Compare against this document

Use this prompt template with the AI assistant:

> Read `way4tech_logistics/PROJECT_TRACKING.md` then compare the new BRD attached below.
> List ONLY items that are genuinely new (not already in Section 3 Requirement Matrix).
> For each new item, tell me:
> 1. Which section of BRD it comes from
> 2. Whether it's a major feature or minor modification
> 3. Estimated dev days
> 4. Whether it depends on something already built
> Skip small modifications, UI polish, and clarifications.
> Format as a clean change-request table I can send to the client.

### Step 3: Update this document

- Add new column `BRD-vN` to the requirement matrix
- Mark each row in the new column: `✓` (already in scope), `new` (needs CR), `minor` (skip)
- Add a new section in Change Log with the delta

### Step 4: Quote the delta

- Sum the estimated days for items marked `new`
- Apply standard rate (SAR 300-400 / day effective)
- Add to billing summary (Section 5) as CR-N
- Update revised total

### Step 5: Send professional change request

Use the draft message template from the previous CR messages — same structure, different content.

---

## Section 8 — File References

| Source Document | Path |
|---|---|
| BRD v1 | `docs/brd_v1_alzain.md` ✅ |
| BRD v2 | `docs/brd_v2_alzain.md` ✅ (CR-1 summary included) |
| BRD v3 | `docs/brd_v3_alzain.md` ✅ (CR-2 summary included) |
| **Work Queue (pending + questions)** | **`docs/WORK_QUEUE.md`** ✅ |

> **IMPORTANT:** `docs/WORK_QUEUE.md` is the live pending-work file. Read it before doing anything. It has Tier A/B/C task details, open questions to client, and decision log.
| **This tracking doc** | `way4tech_logistics/PROJECT_TRACKING.md` |
| Technical reference | `way4tech_logistics/WAY4TECH_LOGISTICS_TECHNICAL_REFERENCE.md` |
| User guide | `way4tech_logistics/WAY4TECH_LOGISTICS_USER_GUIDE.md` |

---

## Section 9 — Maintenance Notes for Future AI Sessions

**To the next session (human or AI):** This document is the authoritative record of what's quoted, what's built, and what's pending for the Alzain Towers project. Before touching any feature:

1. **Check Section 3** to confirm the feature is in scope and what status it has
2. **Check Section 4** for the "extras" list — some things were built for free; don't re-quote them
3. **Check Section 6** for priority order of pending work
4. **Don't assume** the user wants a feature implemented just because they mention it in conversation — many items are pending quote approval
5. **When client feedback arrives** use the Step 1-5 protocol in Section 7

Keep this document updated as the single source of truth. Every new BRD, every change request, every milestone — log it here.

---

*Last updated: 2026-04-16 (session 4 complete — 11 items closed from client's latest feedback, Fleet PDF + Fleet Excel Export + Maintenance Excel Import/Export delivered, 17/23 feedback items done = 74%)*

## Session 4 Summary (2026-04-16)

**Tasks completed:**

**Round 1 — 7 quick wins:**
1. Fleet sequence → simple 10-digit format (1000000001+)
2. Indirect expenses info banner for investor-owned trucks
3. Driver iqama read-only field on trip form
4. Partner CR/Iqama moved to proper "KSA Info" notebook tab
5. Maintenance scan copy binary field (PDF/image upload)
6. Vehicle Models config menu (admin edit/delete)
7. Vehicle type selection extended (+Truck, Bus, Flatbed, Trailer, Heavy, Other)

**Round 2 — 4 Excel/PDF items:**
1. Fleet PDF report (`views/report_fleet_data.xml`) — Print button on fleet form
2. Fleet Excel Export (`wizard/fleet_excel_export.py`) — 29-column download
3. Maintenance Excel Export (`wizard/maintenance_excel_wizard.py`) — filterable
4. Maintenance Excel Import — auto-creates vendors, row-level error log

**Client communication:** Sent short payment request message for Quote v1 completion.

**Next unblocked work (no client input needed):**
- Tier A: PO renewal, repeated repair detection, previous expense display widget, office staff cost fields, invoice category admin control, bill restriction (~7h)
- Tier B: Asset depreciation, ZIP bundle, cashflow email, Fleet Excel Import, Trip Excel Import/Export, graph views (~21h)
- Tier C: Inventory for fleet parts, driver payroll templates (~9h)

**Blocked on client answers:**
- Q1: Trip revenue type "mix" — need screenshot/clarification
- Q2: Salesperson commission rules (4 criteria + multi-person + employee/user)
- Q3: WhatsApp provider for alerts
- Q4-Q12: Secondary clarifications (don't block all work)

**Files added/modified in Session 4:**
- Added: `wizard/fleet_excel_export.py` + `_views.xml`
- Added: `wizard/maintenance_excel_wizard.py` + `_views.xml`
- Added: `views/report_fleet_data.xml`
- Modified: `wizard/__init__.py`, `__manifest__.py`, `security/ir.model.access.csv`, `views/menu_views.xml`, `models/fleet_vehicle_extension.py` (vehicle_type extended + new model), `models/truck_trip.py` (driver_iqama_number related field), `models/fleet_service_extension.py` (scan copy binary), `views/partner_employee_views.xml` (notebook tab), `views/truck_views.xml` (investor banner), `views/truck_trip_views.xml` (driver iqama display), `views/truck_maintenance_views.xml` (scan copy field)
- DB change: `ir_sequence` row for `way4tech.fleet.vehicle` updated to prefix='', padding=10, start=1000000001
