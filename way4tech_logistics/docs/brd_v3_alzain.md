# BRD v3 — Alzain Tower Contracting Est (Expanded)
**Client:**
- Alzain Towers Contracting Company (Main CR)
- Woodpecker Logistic Service Est (Branch)
- Future Power Trading Est (Branch)
- Fame Island Contracting Company (Main CR)
- Mehar Areen Facility Contracting Company (Main CR)

**Project:** Income & Expense Management System in Odoo (Woodpecker Logistic Service Est)
**Odoo Version:** 19.0 (Community Edition)
**Archive source:** Third BRD received from client (preceded CR-2 quote)

---

## 1. Introduction

This document explains the business requirements for implementing an Income and Expense Management System in Odoo (Community Edition). The goal of this system is to manage fleet income, expenses, payroll, investor profit sharing, and financial reporting in a simple and automated way.

## 2. Company Income Sources

- Trucks (3 Company-Owned, 6 Investor-Owned, 2 Installment Buses)
- Manpower (Food Delivery Riders) — own sponsor + freelance
- Manpower (Construction Workers) — all freelancer
- Commission-Based Income (5%)
- **Rented equipment / machinery etc** *(NEW in v3)*

## 3. Financial Fleet Process

### 3.1 Company-Owned Trucks / Buses / Flatbed

**1. Monthly Revenue**

- Each company truck generates monthly rental income. Company monthly revenue is different based on standard hours + overtime hours.
  - *Explanation:* It's simple — we get timesheet from client (basic + overtime) and by following same timesheet we make invoice and salary sheet.
- And sometimes company get PER TRIP BASIS Trucks rental income (e.g., Total trip per month × decided rate = sales revenue).
  - *Explanation:* By considering number of trips we make invoices. For example: Total trip per month × decided rate = sales revenue. And while paying salary to drivers we consider the same number of trips plus basic salary. For example: `(Basic salary) + (Total trip per month × decided rate) = Salary`.
- **Company hired truck from 3rd party and rented to client as middleman as well.** *(NEW in v3)*
- Company provides flatbeds on Fixed rental basis (we are getting per month fixed rent).
- **Company rented yard to another party also.** *(NEW in v3)* We shared yard with another party and get half rent from him.

**2. Direct Expense Deduction**

The following direct expenses shall be deducted from the monthly rental income:
- Basic Salary Driver
- Driver Overtime
- All Maintenance Costs

`Gross Profit = Monthly Rent – Driver Salary – Driver Overtime – Maintenance Cost`

**3. Indirect Expense Deduction**

From the Gross Profit, the company shall deduct operational expenses including:
- Yard Rent (Parking Area)
- Coordinator salary Exp
- Driver + Coordinator iqama cost
- Other Operational Costs

`Net Profit = Gross Profit – Yard Rent – Iqama Cost – Coordinator Salary – Other Operational Expenses`

### 3.2 Investor-Owned Trucks

The Gross Profit for investor-owned trucks shall be calculated using the same formula as company-owned trucks:

`Gross Profit = Monthly Rent – Driver Salary – Driver Overtime – Maintenance Cost`

The calculated Gross Profit shall be distributed equally:
- 50% Investor Share
- 50% Company Share

All operational expenses (yard rent, coordinator salary, driver + coordinator iqama cost, and other operational costs) shall be borne by the company from its 50% share. The investor shall not bear operational expenses.

### 3.3 Installment Tracking for Assets *(NEW section in v3)*

In Odoo, we need a feature to manage monthly installments for assets purchased on installment, such as buses. The system should automatically track each installment, update the outstanding balance, and generate reminders or reports for every due payment.

## 4. Driver Salary Structure

- Basic Salary
- Overtime
- Food Allowance (if applicable)
- Loan Deduction
- Advance Salary Deduction (when company pay salary then will deduct all advances given to drivers till that date)
- Traffic Violation Deduction

`Net Salary = Basic Salary + Overtime – Loan – Advance – Traffic Fine`

**Notes:** We shared separate details excel sheet for salary structure for all (drivers, riders, staff, general manpower).

## 5. Data Import & Automation

### 5.1 Excel Template Upload

Company requires a simplified data entry mechanism to facilitate efficient monthly reporting. The system should provide a template (e.g., Excel format) enabling users to:

- Driver salary + Drivers advances + Fleets diesel usage and any other reoccurring exp, like iqama cost upload to Odoo via excel template
- Upon uploading into Odoo, the system shall automatically create relevant records, compute profit values, and generate reports per vehicle

### 5.2 Invoice Scan Attachments

Company required to add each bill copy into Odoo related to Fleets. For example, if we record any exp we can upload invoice copy also against that entry and when we want to download any report all related invoices automatically download in zip folder with that report.

a. Attach invoice copies with each expense entry
b. Download reports with related invoices
c. **Enable system that we can email / WhatsApp directly to party as well** *(NEW in v3)*

### 5.3 Payroll Module for Office Staff Only

Company needs the payroll module for Office staff only. Only for Office staff set up payroll structure.

**Note:** We need payroll only for office staff but for driver and other manpower workers working at project we will make salary in excel template and upload to Odoo.

### 5.4 VAT Compliance (KSA-15%)

- VAT 15% Configuration
- Input and Output VAT Tracking
- **VAT Reporting Quarterly** *(quarterly specified in v3)*

### 5.5 Inventory Management

- Track Spare Parts, Tires, Oil, Batteries
- Truck-wise maintenance history
- Repeated repair tracking

### 5.6 Purchase Order (PO) Balance Tracking

Company needs customization in Odoo for Purchase Order (PO) balance tracking and auto-closing.

If a client issues a PO of 150,000, the balance should automatically be reduced with each invoice. The system must check the remaining balance before creating an invoice and restrict or warn if the amount exceeds the available balance. Once the full PO amount is utilized, the PO should automatically move to "Closed" status. The PO should clearly display Total Amount, Consumed Amount, and Remaining Balance.

Additionally, when the PO reaches 80–90% utilization and the project is still ongoing, the system should send a notification and allow PO renewal (either by adding value to the same PO or creating a linked new PO).

### 5.7 Mandatory Entry Category System *(NEW in v3)*

- Implement a mandatory category field for all accounting entries in Odoo (bills, journal entries, payments, voucher)
- The system must NOT allow posting any entry without selecting a category (strictly required)
- Categories should be dynamic (e.g., Advance, Loan, Salary Payable, Salary, Rent, Utility Bills, Others, etc.)
- Admin must be able to add, edit, or delete categories anytime

### 5.8 Employee Category-wise Report & Auto Send *(NEW in v3)*

Generate category-wise reports for each employee (driver / rider / staff).

The report should show monthly totals per category (e.g., Advance, Utility Bills, Salary, etc.) and include:

- Total advance taken
- Total utility expenses
- Total salary amount
- Total salary payable
- Reports must be filterable by employee and month

Add an option to automatically send this report:

- Via email
- Or via WhatsApp

There should be a button or automated action to generate and send the report directly to the employee.

### 5.9 Invoice Category with Mandatory Selection & Admin Control *(NEW in v3)*

- Add a dynamic category field in invoices to classify them (e.g., Salesperson, Subcontractor, Project, etc.)
- The category list should be fully editable by the Main Admin at any time (add, edit, delete)
- The system must NOT allow posting or validating an invoice without selecting a category
- Admin should have full control over which users can view or use the categories in invoices

### 5.10 Daily Cash Flow Alerts to Owner *(NEW in v3)*

Send daily following reports automatically to the Owner's mobile with graph (via WhatsApp or Email):

- Cash flow
- Petty cash balance of staff
- Bank Balances
- Total receivable / payable

Reports can be sent:
- Automatically every day / week / month / quarter (auto-scheduled)
- Or manually via a button clicked by Accountant, User, or Admin

### 5.11 Previous Expense Display Feature *(NEW in v3)*

- Whenever any user (Accountant, User, or Admin) posts a ledger entry, bill, or voucher, the system should display the previous related expense for the same item
- The previous expense should be shown below the current entry in a faint / soft color for easy reference
- Example: If the current entry is for a vehicle oil change, the system should show the last oil change expense for that same vehicle below it

This feature should work for all expense-related entries to provide context and history without affecting the posting process.

### 5.12 Asset Depreciation & Residual Value Management *(NEW in v3)*

All assets (Client field, Tools, Machinery, etc.) should have automatic depreciation, with the ability to select the depreciation method (Straight line or Declining balance) and set the residual value, and the system should calculate and update depreciation periodically while showing original value, depreciation amount, and book / residual value in the report.

### 5.13 User Access Control (Expanded)

- Restrict back-date entries
- Restrict deleting transactions
- Restrict ledger creation
- Restrict vendor creation
- Restrict access to Profit & Loss report
- **Restrict some bills** *(NEW in v3)*
- **Implement an approval workflow in Odoo for journal entries** *(NEW in v3)*

**Approval Workflow Details:**

1. When an accountant creates an entry:
   - If amount total > 500 SAR → set state = 'waiting approval', do NOT allow posting, send notification to Main Admin
   - If total amount ≤ 500 SAR → automatically post the entry

2. Main Admin:
   - Can approve → change state to 'posted'
   - Can reject → send back to draft

3. Notes:
   - Alert notification email send to admin for restricted entry
   - Should be recorded in audit trail
   - Rejection option with reason, return to accountant / user for amendment

**Note:** All customization features in the system must have strong user access control, allowing the Admin to fully control which users (Accountants, Users, etc.) can view, use, or post customized features, ensuring 100% restricted access as per Admin configuration.

## 6. Vendors *(NEW section in v3)*

We took generators and other heavy machinery on rent also from different vendors.

## 7. Reports Requirement

1. **Client-wise profitability report for investor's fleets and own fleets + project costing report** for each truck/buses/flatbed (auto calculation, as PDF):
   - Full automation of investor profit sharing
   - Automatically calculate profit per truck
   - Automatically calculate profit per Project
   - Implement analytic reporting per revenue division
   - Provide branch-level profitability reporting

2. **Receivable / Payable Aging Report**

3. **Per-truck maintenance cost tracking** — track each truck maintenance cost (e.g., truck #6280 battery repaired on 2-Jan-2026 and again on 2-Feb-2026):
   - Trailer-wise revenue tracking
   - Trailer-wise expense tracking

4. **Salesperson-wise profitability** — Company needs profitability against each salesperson

5. **Each office staff employee cost** *(NEW in v3)* — salary + SIM + car maintenance cost + fuel + FAT + iqama + insurance + GOSI + Saudization

6. **Each rider + driver ledger management** *(NEW in v3)* — salary + iqama + insurance + GOSI + Saudization, and each rider + driver profit margin:
   - `Employee margin = Revenue per employee – Cost per employee`

7. **Graph / Chart view on ALL reports** *(NEW in v3)* — all reports in the system should have an optional graph / chart view along with the standard tabular / report view

## Extra / Later On — Future Phase (explicitly deferred)

### 1. Purchase Invoice Scanner Integration

- Integrate a scanner with Odoo to automatically capture purchase invoices
- Scanned invoices should directly appear in the system without manual entry
- Admin / User should be able to map which data fields from the invoice are captured by the scanner
- System should validate and process the scanned invoice automatically

### 2. Employee Mobile Thumb Impression Attendance

- Implement a mobile-based thumb impression attendance system for employees
- Employees should be able to mark attendance from their mobile device via a secure app
- Admin should be able to define geofencing parameters:
  - Exact location
  - Radius options (1 km, 5 km, 10 km, etc.)
- Attendance should only be allowed when the employee is within the defined location / radius
- System should automatically record attendance in Odoo and integrate with timesheets
- This system should support employees located in multiple cities / locations

---

## CR-2 — Way4Tech response to BRD v3

**Change Request fee:** SAR 8,500 (on top of Quote-v1 SAR 3,700 + CR-1 SAR 3,500)
**Timeline impact:** +5 to 6 weeks
**Revised Total Project Cost:** SAR 15,700

### New items quoted in CR-2

**A. New Business Lines (5)**
1. Middleman truck rental (3rd-party hire → client)
2. Yard rental income (sub-rental to another party)
3. Equipment / machinery rental TO clients (outbound)
4. Equipment / machinery rental FROM vendors (inbound — generators etc.)
5. Two additional Main CRs (Fame Island + Mehar Areen) — company setup doubles

**B. Accounting Controls (4)**
6. Mandatory Entry Category System on all account moves
7. Invoice Category with mandatory admin-controlled selection
8. Approval workflow for journal entries > 500 SAR
9. Selective bill-level access restriction

**C. Automation & Alerts (3)**
10. Daily / weekly / monthly cash flow alerts to owner via WhatsApp / Email with graph
11. Employee category-wise report with auto-send (email / WhatsApp)
12. Direct email / WhatsApp sending for invoices / reports

**D. UX Features (2)**
13. Previous expense display feature (historical context on new entries)
14. Graph / chart view on ALL reports

**E. Asset Management (1)**
15. Asset Depreciation & Residual Value Management (SL / DB methods)

**F. New Reports (2)**
16. Office Staff Cost Breakdown (salary + SIM + car + fuel + FAT + iqama + insurance + GOSI + Saudization)
17. Rider / Driver Ledger + Profit Margin (Employee Margin = Revenue − Cost)

**Future Phase (NOT in CR-2):**
- Purchase Invoice OCR Scanner Integration → separate quote when needed
- Mobile Thumb Attendance + Geofencing → separate quote when needed
