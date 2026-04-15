# BRD v2 — Alzain Tower Contracting Est
**Client:** Alzain Towers Contracting Company (Main CR)
- Woodpecker Logistic Service Est (Branch)
- Future Power Trading Est (Branch)

**Project:** Income & Expense Management System in Odoo (Woodpecker Logistic Service Est)
**Odoo Version:** 19.0 (Community Edition)
**Archive source:** Second BRD received from client (preceded CR-1 quote)

---

## 1. Introduction

This document explains the business requirements for implementing an Income and Expense Management System in Odoo (Community Edition). The goal of this system is to manage fleet income, expenses, payroll, investor profit sharing, and financial reporting in a simple and automated way.

## 2. Company Income Sources

- Trucks (3 Company-Owned, 6 Investor-Owned, 2 Installment Buses)
- Manpower (Food Delivery Riders) — own sponsor + freelance
- Manpower (Construction Workers) — all freelancer
- Commission-Based Income (5%)

## 3. Financial Fleet Process

### 3.1 Company-Owned Trucks / Buses / Flatbed

**1. Monthly Revenue**
- Each company truck generates monthly rental income. Company monthly revenue is different based on standard hours + overtime hours.
- And sometimes company get PER TRIP BASIS Trucks rental income (e.g., Total trip per month × decided rate = sales revenue).
- Company provides flatbed on Fixed rental basis.

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

## 4. Driver Salary Structure

- Basic Salary
- Overtime
- Food Allowance (if applicable)
- Loan Deduction
- Advance Salary Deduction (when company pay salary then will deduct all advances given to drivers till that date)
- Traffic Violation Deduction

`Net Salary = Basic Salary + Overtime – Loan – Advance – Traffic Fine`

## 5. Data Import & Automation

### 5.1 Excel Template Upload

Company requires a simplified data entry mechanism to facilitate efficient monthly reporting. The system should provide a template (e.g., Excel format) enabling users to:

- Company required that Driver salary + Drivers advances + Fleets diesel usage and any other reoccurring exp, like iqama cost upload to Odoo via excel template
- Upon uploading into Odoo, the system shall automatically create relevant records, compute profit values, and generate reports per vehicle (as shares excel sheet for one driver)

### 5.2 Invoice Scan Attachments

Company required to add each bill copy into Odoo related to Fleets. For example, if we record any exp we can upload invoice copy also against that entry and when we want to download any report all related invoices automatically download in zip folder with that report.

a. Attach invoice copies with each expense entry
b. Download reports with related invoices

### 5.3 Payroll Module for Office Staff Only

Company needs the payroll module for Office staff only. Only for Office staff set up payroll structure.

**Note:** We need payroll only for office staff but for driver and other manpower workers working at project we will make salary in excel template and upload to Odoo as mentioned above.

### 5.4 VAT Compliance (KSA-15%)

- VAT 15% Configuration
- Input and Output VAT Tracking
- VAT Reporting

### 5.5 Inventory Management

- Track Spare Parts, Tires, Oil, Batteries
- Truck-wise maintenance history
- Repeated repair tracking

### 5.6 Purchase Order (PO) Balance Tracking

Company need a customization in Odoo for Purchase Order (PO) balance tracking and auto-closing.

If a client issues a PO of 150,000, the balance should automatically reduce with each invoice. The system must check the remaining balance before creating an invoice and restrict or warn if the amount exceeds the available balance. Once the full PO amount is utilized, the PO should automatically move to "Closed" status. The PO should clearly display Total Amount, Consumed Amount, and Remaining Balance.

Additionally, when the PO reaches 80–90% utilization and the project is still ongoing, the system should send a notification and allow PO renewal (either by adding value to the same PO or creating a linked new PO).

### 5.7 User Access Control

- Restrict back-date entries
- Restrict deleting transactions
- Restrict ledger creation
- Restrict vendor creation
- Restrict access to Profit & Loss report

## 7. Reports Requirement

1. **Client-wise profitability report for investor's fleets and own fleets + project costing report** for each truck/buses/flatbed (auto calculation, as PDF):
   - Full automation of investor profit sharing
   - Automatically calculate profit per truck
   - Automatically calculate profit per Project
   - Implement analytic reporting per revenue division
   - Provide branch-level profitability reporting

2. **Receivable / Payable Aging Report**

3. **Per-truck maintenance cost tracking** — Company needs to track each truck maintenance cost (e.g., one truck #6280 battery repaired on 2-Jan-2026 and again same exp incurred on same truck on 2-Feb-2026):
   - Trailer-wise revenue tracking
   - Trailer-wise expense tracking

4. **Salesperson-wise profitability** — Company needs profitability against each salesperson

---

## CR-1 — Way4Tech response to BRD v2

**Change Request fee:** SAR 3,500 (on top of Quote-v1 SAR 3,700)
**Timeline impact:** +2 to 3 weeks
**Total revised project cost:** SAR 7,200

### New items quoted in CR-1

| # | Item | Category |
|---|---|---|
| 1 | Installment Bus Tracking (2 units) + monthly schedule + payoff | Fleet |
| 2 | Indirect Expense Layer (yard rent + coordinator + iqama + other) with Net Profit formula | Profitability |
| 3 | Detailed truck revenue formulas (Hours+OT / Per-Trip × Rate / Flatbed Fixed Rental) | Trip |
| 4 | Invoice / bill scan attachments + ZIP bundle with reports | Attachments |
| 5 | Inventory for fleet parts (spare parts, tires, oil, batteries) + repeat detection | Inventory |
| 6 | PO 80-90% alert + renewal workflow (basic PO check was in v1) | PO |
| 7 | Salesperson-wise profitability report | Reporting |
