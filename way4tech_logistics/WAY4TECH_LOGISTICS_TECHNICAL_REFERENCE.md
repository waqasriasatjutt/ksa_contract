# Way4Tech Logistics — Technical Reference
## Module: `way4tech_logistics` | Odoo 19 Community | Version 19.0.1.0.0

> **Purpose of this document:** Complete technical reference of everything built in this module.
> Share this with Claude (or any AI) at the start of a session before requesting changes.

---

## 1. Module Overview

A custom Odoo 19 Community module for a multi-branch logistics & manpower company in KSA.

**Key features:**
1. Rider salary Excel import → standard `hr.payslip` payroll
2. Commission-based invoicing with KSA 15% VAT
3. Truck/fleet management with investor profit sharing
4. Truck trip / rental tracking with PO limit
5. Truck maintenance logs with vendor bills
6. Employee KSA cost tracking (GOSI, Iqama, Insurance, Saudization)
7. Manpower billing contracts (fixed + hourly)

**Dependencies:** `hr_payroll_community`, `hr_payroll_account_community`, `account`, `analytic`, `mail`

> ⚠️ **IMPORTANT — Odoo 19 Compatibility Notes:**
> - `res.groups` does NOT have `category_id` or `users` fields in Odoo 19 — never add them
> - `res.users` does NOT have `groups_id` field in Odoo 19 — never assign users to groups via XML
> - `<group expand="0">` is INVALID in Odoo 19 search views — use flat `<filter>` elements instead
> - Payroll contract model is `hr.version` (NOT `hr.contract`) in `hr_payroll_community`
> - `column_invisible` in list views is evaluated at **column level** — cannot reference row-level fields like `rider_type`

---

## 2. File Structure

```
way4tech_logistics/
├── __manifest__.py
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── commission_receipt.py      # way4tech.commission.receipt
│   ├── employee_cost.py           # way4tech.employee.cost
│   ├── manpower_contract.py       # way4tech.manpower.contract
│   │                              # way4tech.manpower.contract.line
│   │                              # way4tech.manpower.timesheet
│   ├── salary_import.py           # way4tech.salary.import
│   ├── salary_import_line.py      # way4tech.salary.import.line
│   ├── truck.py                   # way4tech.truck
│   │                              # way4tech.investor.payable
│   ├── truck_maintenance.py       # way4tech.truck.maintenance
│   └── truck_trip.py              # way4tech.truck.trip
├── wizard/
│   ├── __init__.py
│   ├── salary_excel_import.py     # way4tech.salary.excel.import (TransientModel)
│   └── salary_excel_import_views.xml
├── views/
│   ├── commission_receipt_views.xml
│   ├── employee_cost_views.xml
│   ├── manpower_contract_views.xml
│   ├── menu_views.xml
│   ├── salary_import_views.xml
│   ├── truck_maintenance_views.xml
│   ├── truck_trip_views.xml
│   └── truck_views.xml
├── security/
│   ├── security.xml               # Two groups: logistics_manager, logistics_user
│   └── ir.model.access.csv        # ACL for all 11 models
├── data/
│   ├── sequence_data.xml          # 6 sequences
│   └── salary_structure_data.xml  # RIDER salary structure + 8 rules
└── static/description/
    └── icon.png
```

**Manifest data load order** (important — wizard must come before salary_import_views):
```python
'security/security.xml',
'security/ir.model.access.csv',
'data/sequence_data.xml',
'data/salary_structure_data.xml',
'wizard/salary_excel_import_views.xml',   # BEFORE salary_import_views
'views/salary_import_views.xml',
'views/commission_receipt_views.xml',
'views/truck_views.xml',
'views/truck_trip_views.xml',
'views/truck_maintenance_views.xml',
'views/employee_cost_views.xml',
'views/manpower_contract_views.xml',
'views/menu_views.xml',
```

---

## 3. Security

### Groups (`security/security.xml`)
```xml
way4tech_logistics.group_logistics_manager  — full CRUD on all models
way4tech_logistics.group_logistics_user     — read-only on most models
```
> ⚠️ Groups have only `name` and `implied_ids`. No `category_id`, no `users` field.
> Menu items have NO `groups=` attribute (Odoo 19 cannot assign users via XML).

### ACL (`security/ir.model.access.csv`)
All 11 models have manager (CRUD) + user (read-only) rows:
- `way4tech.salary.import`
- `way4tech.salary.import.line`
- `way4tech.commission.receipt`
- `way4tech.salary.excel.import`
- `way4tech.truck`
- `way4tech.investor.payable`
- `way4tech.employee.cost`
- `way4tech.manpower.contract`
- `way4tech.manpower.contract.line`
- `way4tech.manpower.timesheet`
- `way4tech.truck.trip`
- `way4tech.truck.maintenance`

---

## 4. Sequences (`data/sequence_data.xml`)

| Sequence Code | Prefix | Example |
|---|---|---|
| `way4tech.salary.import` | `WAY4TECH/SAL/IMP/{year}/` | WAY4TECH/SAL/IMP/2026/0001 |
| `way4tech.commission.receipt` | `WAY4TECH/COM/{year}/` | WAY4TECH/COM/2026/0001 |
| `way4tech.investor.payable` | `WAY4TECH/INV/{year}/` | WAY4TECH/INV/2026/0001 |
| `way4tech.employee.cost` | `WAY4TECH/EMP/COST/{year}/` | WAY4TECH/EMP/COST/2026/0001 |
| `way4tech.truck.trip` | `WAY4TECH/TRIP/{year}/` | WAY4TECH/TRIP/2026/0001 |
| `way4tech.truck.maintenance` | `WAY4TECH/MAINT/{year}/` | WAY4TECH/MAINT/2026/0001 |

All sequences use `company_id = base.main_company`, padding=4.

---

## 5. Salary Structure (`data/salary_structure_data.xml`)

**Structure:** `RIDER` — "Rider Payroll"

**Salary Rule Categories (custom):**
- `RIDER_EARN` — Rider Earnings
- `RIDER_DED_CAT` — Rider Deductions
- `RIDER_NET_CAT` — Rider Net

**Rules:**

| Rule Code | Name | Category | Formula |
|---|---|---|---|
| `RIDER_BASIC` | Basic Salary | RIDER_EARN | `contract.wage` |
| `RIDER_ORDER` | Order Earnings | RIDER_EARN | `inputs.ORDER_EARN.amount` |
| `RIDER_BONUS_RULE` | Bonus | RIDER_EARN | `inputs.RIDER_BONUS.amount` |
| `RIDER_PETROL_RULE` | Petrol Allowance | RIDER_EARN | `inputs.RIDER_PETROL.amount` |
| `RIDER_DED_RULE` | Deduction | RIDER_DED_CAT | `-inputs.RIDER_DED.amount` |
| `RIDER_ADV_DED_RULE` | Advance Deduction | RIDER_DED_CAT | `-inputs.RIDER_ADV_DED.amount` |
| `RIDER_FINE_RULE` | Fine | RIDER_DED_CAT | `-inputs.RIDER_FINE.amount` |
| `RIDER_NET` | Net Salary | RIDER_NET_CAT | `categories.RIDER_EARN + categories.RIDER_DED_CAT` |

---

## 6. Models — Detailed Reference

---

### 6.1 `way4tech.salary.import` — Rider Salary Import
**File:** `models/salary_import.py`

**Fields:**

| Field | Type | Notes |
|---|---|---|
| `name` | Char | Auto-sequence, readonly |
| `date` | Date | Import date, default today |
| `period_start` | Date | Payroll period start |
| `period_end` | Date | Payroll period end |
| `client_id` | Many2one `res.partner` | Client/customer |
| `analytic_account_id` | Many2one `account.analytic.account` | |
| `company_id` | Many2one `res.company` | |
| `currency_id` | Many2one (related company) | |
| `state` | Selection | draft → imported → payslips_created → done |
| `line_ids` | One2many → `way4tech.salary.import.line` | |
| `payslip_run_id` | Many2one `hr.payslip.run` | Set after payslip creation |
| `total_employees` | Integer | Computed: lines with employee_id |
| `total_net` | Monetary | Computed: sum of net_payable |
| `error_count` | Integer | Computed: lines with has_error=True |
| `notes` | Text | |

**State Machine:**
```
draft → [Import from Excel] → imported → [Create Payslips] → payslips_created → [Confirm Payslips] → done
```

**Key Methods:**
- `action_open_import_wizard()` — opens `way4tech.salary.excel.import` wizard in `new` window, passes `{'default_import_id': self.id}`
- `action_create_payslips()` — splits lines into `employee_lines` and `freelancer_lines`:
  - **Employee lines:** creates `hr.payslip.run` + `hr.payslip` + `hr.payslip.input` records. Contract lookup via `hr.version` model with states `['open', 'draft', 'new', 'pending']`
  - **Freelancer lines:** creates `account.move` (vendor bill, `move_type='in_invoice'`) to `line.vendor_id`. If `vendor_id` is not set, marks line as error.
  - Payslip input codes: `ORDER_EARN`, `RIDER_BONUS`, `RIDER_PETROL`, `RIDER_DED`, `RIDER_ADV_DED`, `RIDER_FINE`
- `action_confirm_payslips()` — calls `payslip.action_payslip_done()` on all draft payslips, sets state = done
- `action_view_payslips()` — opens the linked `hr.payslip.run` form

---

### 6.2 `way4tech.salary.import.line` — Salary Import Line
**File:** `models/salary_import_line.py`

**Fields:**

| Field | Type | Notes |
|---|---|---|
| `import_id` | Many2one `way4tech.salary.import` | Parent, cascade delete |
| `sequence` | Integer | Handle widget |
| `employee_name` | Char | Name from Excel, used if employee not found |
| `employee_id` | Many2one `hr.employee` | Linked employee |
| `rider_type` | Selection | `employee` / `freelancer` |
| `vendor_id` | Many2one `res.partner` | Required for freelancers (domain: supplier_rank > 0) |
| `fixed_salary` | Float | |
| `order_earnings` | Float | |
| `bonus` | Float | |
| `petrol` | Float | |
| `deduction` | Float | |
| `advance_deduction` | Float | |
| `fine` | Float | |
| `gross_earnings` | Float | Computed: fixed + order + bonus + petrol |
| `total_deductions` | Float | Computed: deduction + advance + fine |
| `net_payable` | Float | Computed: gross - total_deductions |
| `payslip_id` | Many2one `hr.payslip` | Set after payslip creation (employees only) |
| `freelancer_bill_id` | Many2one `account.move` | Set after bill creation (freelancers only) |
| `has_error` | Boolean | Red decoration in list |
| `error_message` | Char | |
| `note` | Char | |

**Decorations in list view:**
- Red (`decoration-danger`): `has_error == True`
- Green (`decoration-success`): `payslip_id != False`
- Muted (`decoration-muted`): no error and no payslip

---

### 6.3 `way4tech.salary.excel.import` — Excel Import Wizard
**File:** `wizard/salary_excel_import.py`
**Type:** TransientModel

**Fields:** `import_id`, `excel_file` (Binary), `file_name` (Char)

**Excel format expected (row 2 onwards):**

| Col A | Col B | Col C | Col D | Col E | Col F | Col G | Col H | Col I | Col J |
|---|---|---|---|---|---|---|---|---|---|
| Employee Name | rider_type | Fixed Salary | Order Earnings | Bonus | Petrol | Deduction | Advance Ded. | Fine | Notes |

- Row 1 = header (skipped)
- Col B: `freelancer` or `free` → freelancer, anything else → employee
- Employee matched by name (`ilike` search on `hr.employee`)
- If not found → `has_error=True`, `error_message='Employee not found: ...'`
- Clears existing lines before importing new ones
- Sets import state to `imported` on success

**Requires:** `openpyxl` Python library (`pip install openpyxl` in Docker)

---

### 6.4 `way4tech.commission.receipt` — Commission Receipt
**File:** `models/commission_receipt.py`

**Fields:**

| Field | Type | Notes |
|---|---|---|
| `name` | Char | Auto-sequence |
| `date` | Date | |
| `partner_id` | Many2one `res.partner` | Customer (who pays the full amount) |
| `subcontractor_id` | Many2one `res.partner` | Subcontractor (domain: supplier_rank > 0) |
| `receipt_amount` | Monetary | Full receipt including VAT |
| `vat_rate` | Float | Default 15.0 |
| `receipt_excl_vat` | Monetary | Computed: `receipt_amount / (1 + vat_rate/100)` |
| `commission_rate` | Float | Default 5.0 |
| `commission_amount` | Monetary | Computed: `receipt_excl_vat × commission_rate / 100` |
| `vat_amount` | Monetary | Computed: `commission_amount × vat_rate / 100` |
| `total_invoice_amount` | Monetary | Computed: `commission_amount + vat_amount` |
| `subcontractor_payable` | Monetary | Computed: `receipt_amount - total_invoice_amount` |
| `state` | Selection | draft → confirmed → invoiced → settled |
| `invoice_id` | Many2one `account.move` | Linked customer invoice |
| `journal_id` | Many2one `account.journal` | Domain: type in ['sale'] |
| `period` | Char | Text reference |
| `is_paid_to_subcontractor` | Boolean | |
| `subcontractor_payment_date` | Date | |
| `subcontractor_payment_ref` | Char | |
| `notes` | Text | |

**Commission Formula (KSA VAT-embedded):**
```
receipt_excl_vat = receipt_amount / (1 + 0.15) = receipt_amount / 1.15
commission       = receipt_excl_vat × commission_rate / 100
vat_on_commission = commission × vat_rate / 100
total_invoice    = commission + vat_on_commission
subcontractor_payable = receipt_amount - total_invoice
```

**Example:** Receipt = 11,500 SAR, commission = 5%, VAT = 15%
- Ex-VAT = 11,500 / 1.15 = 10,000
- Commission = 10,000 × 5% = 500
- VAT on commission = 500 × 15% = 75
- Invoice amount = 575
- Subcontractor payable = 11,500 − 575 = 10,925

**Key Methods:**
- `action_create_invoice()` — creates `out_invoice` to **`subcontractor_id`** (NOT partner_id). Searches for sale tax with `amount = vat_rate`. Raises `UserError` if no tax found.
- `action_mark_subcontractor_paid()` — sets `is_paid_to_subcontractor=True`, records today as payment date

---

### 6.5 `way4tech.truck` — Truck / Fleet
**File:** `models/truck.py`

**Fields:**

| Field | Type | Notes |
|---|---|---|
| `name` | Char | Truck name |
| `license_plate` | Char | |
| `model` | Char | Vehicle model |
| `manufacture_year` | Char | |
| `ownership_type` | Selection | `own` / `investor` |
| `investor_id` | Many2one `res.partner` | Visible only if investor |
| `profit_share_rate` | Float | Default 70.0% |
| `po_limit` | Monetary | Max revenue per trip (0 = no limit) |
| `analytic_account_id` | Many2one `account.analytic.account` | |
| `company_id` | Many2one `res.company` | |
| `currency_id` | Many2one (related) | |
| `state` | Selection | `active` / `maintenance` / `inactive` |
| `current_client_id` | Many2one `res.partner` | Current assignment |
| `notes` | Text | |
| `payout_ids` | One2many → `way4tech.investor.payable` | |
| `payout_count` | Integer | Computed |
| `trip_ids` | One2many → `way4tech.truck.trip` | |
| `trip_count` | Integer | Computed |
| `maintenance_ids` | One2many → `way4tech.truck.maintenance` | |
| `maintenance_count` | Integer | Computed |

**State buttons:** Set Active / Set Maintenance / Set Inactive
**Stat buttons in form:** Trips count, Maintenance count, Investor Payables count (investor only)

---

### 6.6 `way4tech.investor.payable` — Investor Payable
**File:** `models/truck.py` (same file as truck)

**Fields:**

| Field | Type | Notes |
|---|---|---|
| `name` | Char | Auto-sequence |
| `truck_id` | Many2one `way4tech.truck` | |
| `investor_id` | Many2one `res.partner` | Related from truck |
| `period_start` / `period_end` | Date | |
| `total_revenue` | Monetary | Manual entry |
| `total_expenses` | Monetary | Manual entry |
| `net_profit` | Monetary | Computed: revenue - expenses |
| `profit_share_rate` | Float | Related from truck |
| `investor_amount` | Monetary | Computed: net_profit × rate / 100 |
| `company_amount` | Monetary | Computed: net_profit - investor_amount |
| `state` | Selection | draft → confirmed → paid |
| `bill_id` | Many2one `account.move` | Vendor bill created via button |
| `payment_date` | Date | |
| `notes` | Text | |

**Key Methods:**
- `action_create_bill()` — creates `in_invoice` to `investor_id`, line = "Investor Profit Share - {name}", amount = `investor_amount`

---

### 6.7 `way4tech.truck.trip` — Truck Trip / Rental
**File:** `models/truck_trip.py`

**Fields:**

| Field | Type | Notes |
|---|---|---|
| `name` | Char | Auto-sequence |
| `truck_id` | Many2one `way4tech.truck` | |
| `client_id` | Many2one `res.partner` | |
| `trip_date` | Date | |
| `trip_type` | Selection | `delivery` / `rental` / `other` |
| `origin` | Char | |
| `destination` | Char | |
| `distance_km` | Float | |
| `revenue` | Monetary | |
| `driver_id` | Many2one `hr.employee` | |
| `analytic_account_id` | Many2one `account.analytic.account` | |
| `company_id` | Many2one `res.company` | |
| `currency_id` | Many2one (related) | |
| `state` | Selection | draft → confirmed → done / cancelled |
| `notes` | Text | |

**PO Limit Check:**
```python
def _check_po_limit(self):
    if truck.po_limit and rec.revenue > truck.po_limit:
        raise UserError('Trip revenue exceeds PO limit set on truck')
```
Called in `action_confirm()` only. Draft can exceed limit (validation at confirm).

---

### 6.8 `way4tech.truck.maintenance` — Truck Maintenance Log
**File:** `models/truck_maintenance.py`

**Fields:**

| Field | Type | Notes |
|---|---|---|
| `name` | Char | Auto-sequence |
| `truck_id` | Many2one `way4tech.truck` | |
| `maintenance_date` | Date | |
| `maintenance_type` | Selection | `preventive` / `corrective` / `accident` / `other` |
| `description` | Text | Required |
| `vendor_id` | Many2one `res.partner` | Service vendor (supplier_rank > 0) |
| `cost` | Monetary | |
| `bill_id` | Many2one `account.move` | Vendor bill |
| `analytic_account_id` | Many2one `account.analytic.account` | |
| `company_id` / `currency_id` | | |
| `state` | Selection | draft → confirmed → done |
| `notes` | Text | |

**Auto Truck Status:**
- `action_confirm()` → sets `truck_id.state = 'maintenance'` if truck was active
- `action_done()` → sets `truck_id.state = 'active'` if truck was in maintenance

**Key Methods:**
- `action_create_bill()` — requires `vendor_id` and `cost > 0`, creates `in_invoice`
- `action_view_bill()` — opens linked bill

---

### 6.9 `way4tech.employee.cost` — Employee KSA Cost
**File:** `models/employee_cost.py`

**Fields:**

| Field | Type | Notes |
|---|---|---|
| `name` | Char | Auto-sequence |
| `employee_id` | Many2one `hr.employee` | |
| `employee_type` | Selection | `employee` / `freelancer` |
| `period_start` / `period_end` | Date | |
| `client_id` | Many2one `res.partner` | Assigned client |
| `analytic_account_id` | Many2one `account.analytic.account` | |
| `company_id` / `currency_id` | | |
| `basic_salary` | Monetary | |
| `gosi_rate` | Float | Default 11.75% (KSA employer GOSI rate) |
| `gosi_amount` | Monetary | Manual or auto-calculated |
| `iqama_amount` | Monetary | Residency/Iqama cost |
| `insurance_amount` | Monetary | Medical insurance |
| `saudization_amount` | Monetary | Nitaqat/Saudization cost |
| `other_costs` | Monetary | |
| `total_cost` | Monetary | Computed: sum of all costs |
| `state` | Selection | draft / confirmed |
| `notes` | Text | |

**GOSI Auto-Calc:**
- Button "Auto-Calculate GOSI" placed in a `<div>` above the Cost Components group
- Calls `action_compute_gosi()` → `self.gosi_amount = self.basic_salary × self.gosi_rate / 100`
- KSA standard employer GOSI rate = 11.75%

---

### 6.10 `way4tech.manpower.contract` — Manpower Billing Contract
**File:** `models/manpower_contract.py`

**Fields:**

| Field | Type | Notes |
|---|---|---|
| `name` | Char | Required |
| `client_id` | Many2one `res.partner` | |
| `contract_type` | Selection | `food_delivery` / `project` |
| `billing_type` | Selection | `fixed` / `hourly` |
| `fixed_amount` | Monetary | Used for fixed billing |
| `hourly_rate` | Monetary | Used for hourly billing |
| `start_date` / `end_date` | Date | |
| `analytic_account_id` | Many2one `account.analytic.account` | |
| `company_id` / `currency_id` | | |
| `state` | Selection | draft → active → completed / cancelled |
| `line_ids` | One2many → `way4tech.manpower.contract.line` | Assigned workers |
| `timesheet_ids` | One2many → `way4tech.manpower.timesheet` | Hours logged |
| `invoice_ids` | Many2many `account.move` | All invoices created |
| `invoice_count` | Integer | Computed |
| `total_hours` | Float | Computed from timesheets |
| `total_invoiced` | Monetary | Computed: sum of invoice `amount_untaxed` |
| `notes` | Text | |

**Invoice Creation Logic (`action_create_invoice`):**
```python
if billing_type == 'fixed':
    amount = self.fixed_amount
    description = 'Fixed Price - {name}'
else:  # hourly
    amount = self.total_hours * self.hourly_rate
    description = 'Hourly Rate ({hours} hrs x {rate}) - {name}'

# Zero amount guard:
if not amount:
    raise UserError('Invoice amount is zero...')
```
Invoice is `out_invoice` to `client_id`.

### 6.11 `way4tech.manpower.contract.line` — Manpower Line

| Field | Notes |
|---|---|
| `contract_id` | Parent |
| `employee_id` | hr.employee |
| `employee_type` | permanent / freelancer |
| `vendor_id` | res.partner (supplier), for freelancers |
| `role` | Text position |
| `start_date` / `end_date` | |
| `daily_cost` | Monetary |

### 6.12 `way4tech.manpower.timesheet` — Timesheet Entry

| Field | Notes |
|---|---|
| `contract_id` | Parent |
| `date` | Default today |
| `employee_id` | |
| `description` | |
| `hours` | Float |
| `approved` | Boolean |

---

## 7. Menus Structure

```
Way4Tech Logistics (root, sequence=50)
├── Payroll (sequence=10)
│   ├── Salary Imports          → action_salary_import
│   ├── Payroll Batches         → hr_payroll_community.hr_payslip_run_action
│   └── Employee Costs          → action_employee_cost
├── Commission (sequence=20)
│   └── Commission Receipts     → action_commission_receipt
├── Fleet & Trucks (sequence=30)
│   ├── Trucks                  → action_truck
│   ├── Trips                   → action_truck_trip
│   ├── Maintenance             → action_truck_maintenance
│   └── Investor Payables       → action_investor_payable
├── Manpower (sequence=40)
│   └── Manpower Contracts      → action_manpower_contract
└── Configuration (sequence=100)
    ├── Salary Structures       → hr_payroll_community.hr_payroll_structure_action
    └── Salary Rules            → hr_payroll_community.hr_salary_rule_action
```

---

## 8. Known Constraints & Design Decisions

1. **No group restrictions on menus** — Odoo 19 cannot assign users to groups via XML. Security is enforced via `ir.model.access.csv` only.

2. **`hr.version` not `hr.contract`** — `hr_payroll_community` uses `hr.version` as the contract model. Contract state search uses `['open', 'draft', 'new', 'pending']`.

3. **Commission invoice to subcontractor** — The invoice is created for the subcontractor (`subcontractor_id`), not the customer (`partner_id`). The subcontractor pays the commission to the company.

4. **Freelancer vendor bills** — Freelancer salary lines create `in_invoice` (vendor bill) to `vendor_id` on the import line. If `vendor_id` is not set, the line is marked as error.

5. **PO limit check** — Only enforced at `action_confirm()` on trips, not at draft save.

6. **Maintenance auto-status** — `action_confirm()` sets truck to maintenance status. `action_done()` restores to active. Manual override via Set Active / Set Maintenance buttons on the truck form.

7. **openpyxl required** — The Excel import wizard requires `openpyxl`. In Docker: `pip install openpyxl` inside the container.

8. **`column_invisible` limitation** — Cannot reference row-level fields (like `rider_type`) in `column_invisible` on list columns. This causes an Odoo 19 OWL error. Use `optional="hide"` instead for optional columns.

9. **Salary structure company** — `salary_structure_data.xml` uses `ref="base.main_company"`. If multi-company is used, structure may need to be replicated per company.

10. **`hr.payslip.run` has no `company_id`** — The `hr_payroll_community` payslip run model does not have a `company_id` field. Do not add it when creating payslip runs.

---

## 9. Quick Model Name Reference

| Technical Name | Description | Key File |
|---|---|---|
| `way4tech.salary.import` | Salary Import Header | salary_import.py |
| `way4tech.salary.import.line` | Salary Import Line | salary_import_line.py |
| `way4tech.salary.excel.import` | Excel Upload Wizard | wizard/salary_excel_import.py |
| `way4tech.commission.receipt` | Commission Receipt | commission_receipt.py |
| `way4tech.truck` | Truck / Fleet | truck.py |
| `way4tech.investor.payable` | Investor Payable | truck.py |
| `way4tech.truck.trip` | Truck Trip | truck_trip.py |
| `way4tech.truck.maintenance` | Maintenance Log | truck_maintenance.py |
| `way4tech.employee.cost` | Employee KSA Cost | employee_cost.py |
| `way4tech.manpower.contract` | Manpower Contract | manpower_contract.py |
| `way4tech.manpower.contract.line` | Contract Worker Line | manpower_contract.py |
| `way4tech.manpower.timesheet` | Timesheet Entry | manpower_contract.py |
