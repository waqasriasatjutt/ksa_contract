# Way4Tech Logistics – Full User Guide

**Module:** `way4tech_logistics`
**Version:** 19.0.1.0.0
**Platform:** Odoo 19 Community
**Prepared by:** Way4Tech

---

## Table of Contents

1. [Module Overview](#1-module-overview)
2. [Prerequisites & Initial Setup](#2-prerequisites--initial-setup)
3. [Menu Structure](#3-menu-structure)
4. [Rider Salary Import → Payroll](#4-rider-salary-import--payroll)
5. [Commission-Based Invoicing](#5-commission-based-invoicing)
6. [Fleet & Truck Management](#6-fleet--truck-management)
7. [Investor Profit Payables](#7-investor-profit-payables)
8. [Employee Additional Costs (KSA)](#8-employee-additional-costs-ksa)
9. [Manpower Billing Contracts](#9-manpower-billing-contracts)
10. [Configuration](#10-configuration)
11. [Excel Template Reference](#11-excel-template-reference)
12. [Status Reference (All Workflows)](#12-status-reference-all-workflows)
13. [Common Errors & Fixes](#13-common-errors--fixes)

---

## 1. Module Overview

**Way4Tech Logistics** is a custom Odoo 19 module that covers business operations not available in Odoo Community:

| Feature | What It Does |
|---------|-------------|
| **Rider Salary Import** | Import Excel salary sheets and push them into Odoo's standard payroll (hr.payslip) automatically |
| **Commission Invoicing** | Record full client receipts, auto-calculate commission + VAT (KSA 15%), track subcontractor payable |
| **Truck / Fleet Management** | Track company-owned and investor-owned trucks, assign to clients, manage maintenance state |
| **Investor Profit Payables** | Monthly profit-sharing calculations for investor trucks — generate vendor bills automatically |
| **Employee Cost Tracking** | Record KSA-specific employee costs per month (GOSI, Iqama, Insurance, Saudization) |
| **Manpower Contracts** | Create billing contracts for manpower supply (fixed-price or hourly), log timesheets, generate invoices |

---

## 2. Prerequisites & Initial Setup

### 2.1 Required Odoo Modules (must be installed first)
Before installing `way4tech_logistics`, make sure these are installed:

- `hr_payroll_community` (Cybrosys HR Payroll)
- `hr_payroll_account_community` (Payroll Accounting)
- `account` (Accounting)
- `analytic` (Analytic Accounting)
- `mail` (Discuss/Chatter)

### 2.2 Python Library
The Excel import feature requires **openpyxl**. Run this command inside the Odoo Docker container:

```bash
docker exec -it <your_container_name> pip install openpyxl
```

Then restart the container.

### 2.3 Install the Module
1. Go to **Apps** in Odoo
2. Search for **Way4Tech Logistics**
3. Click **Install**
4. After installation, click the **Way4Tech Logistics** icon on the home screen

### 2.4 One-Time Setup After Install

**Step 1 – Create Analytic Accounts** (for profitability tracking per client/project):
- Go to **Accounting → Configuration → Analytic Accounts**
- Create one account per client (e.g., "HungerStation", "Keeta", "L&T Project")

**Step 2 – Set Up the Rider Payroll Salary Structure:**
- Go to **Way4Tech Logistics → Configuration → Salary Structures**
- The structure **"Rider Payroll" (code: RIDER)** is created automatically on install
- Verify it contains these 8 rules: Basic Salary, Order Earnings, Bonus, Petrol Allowance, Deduction, Advance Deduction, Fine, Net Salary

**Step 3 – Assign Rider Structure to Employee Contracts:**
- Go to **Payroll → Employees → Contracts**
- Open each rider's contract
- Set **Salary Structure** = **Rider Payroll**
- Set the **Wage** = the employee's fixed monthly salary

**Step 4 – Set Subcontractors as Vendors:**
- Go to **Contacts**
- Open each subcontractor's contact card
- Tick **"Is a Vendor"** (supplier_rank > 0) so they appear in the Commission module

---

## 3. Menu Structure

```
Way4Tech Logistics (Home App)
│
├── Payroll
│   ├── Salary Imports          ← Import Excel, create & confirm payslips
│   ├── Payroll Batches         ← View all hr.payslip.run batches
│   └── Employee Costs          ← GOSI, Iqama, Insurance per employee
│
├── Commission
│   └── Commission Receipts     ← Full receipt → commission invoice → subcontractor payable
│
├── Fleet & Trucks
│   ├── Trucks                  ← Company & investor truck registry
│   └── Investor Payables       ← Monthly profit distribution to investors
│
├── Manpower
│   └── Manpower Contracts      ← Client billing contracts (fixed or hourly)
│
└── Configuration
    ├── Salary Structures       ← Rider Payroll structure
    └── Salary Rules            ← Individual salary rules
```

---

## 4. Rider Salary Import → Payroll

This is the core payroll feature. It replaces manual payslip entry — you import an Excel file and the system creates all payslips automatically.

### 4.1 Prepare the Excel File

The Excel file must follow this exact column order (Row 1 = headers, data starts Row 2):

| Col A | Col B | Col C | Col D | Col E | Col F | Col G | Col H | Col I | Col J |
|-------|-------|-------|-------|-------|-------|-------|-------|-------|-------|
| Employee Name | Type | Fixed Salary | Order Earnings | Bonus | Petrol | Deduction | Advance Deduction | Fine | Notes |

**Rules:**
- **Col A (Employee Name):** Must match exactly (or closely) the employee name in Odoo HR
- **Col B (Type):** Type `employee` for company-sponsored staff, `freelancer` for outsourced riders
- **Col C–I:** Numeric values. Leave blank or enter 0 if not applicable
- **Col J:** Optional internal note
- Row 1 is always the header row — do not put data there

**Example:**

| A | B | C | D | E | F | G | H | I | J |
|---|---|---|---|---|---|---|---|---|---|
| Ahmed Ali | employee | 1500 | 800 | 200 | 100 | 0 | 250 | 0 | HungerStation |
| Mohammed Saleh | employee | 1500 | 600 | 0 | 100 | 50 | 0 | 0 | |
| Freelancer 1 | freelancer | 0 | 900 | 0 | 0 | 0 | 0 | 0 | Keeta |

### 4.2 Step-by-Step: Import Salaries

**Step 1 – Create a new Salary Import:**
- Go to **Way4Tech Logistics → Payroll → Salary Imports**
- Click **New**
- Fill in:
  - **Import Date:** Today's date
  - **Period Start:** First day of salary period (e.g., 01/03/2026)
  - **Period End:** Last day of salary period (e.g., 31/03/2026)
  - **Client:** The food delivery company (e.g., HungerStation) — optional
  - **Analytic Account:** Select the relevant analytic account for cost tracking
- Click **Save**

**Step 2 – Import the Excel file:**
- Click the **"Import from Excel"** button (only visible in Draft state)
- A dialog opens
- Click the upload icon next to **"Excel File (.xlsx)"**
- Select your prepared Excel file
- Click **"Import"**
- The system reads all rows and creates lines in the **Salary Lines** tab

**Step 3 – Review imported lines:**
- Lines highlighted in **RED** = errors (employee not found in Odoo)
- Lines highlighted in **GREEN** = payslip already created
- Lines with **no color** = valid, ready to process

**For red (error) lines:**
- Click on the line to open it
- Check the **Error Message** field (e.g., "Employee not found: Ahmed Ali")
- Either fix the employee name in the line to match Odoo, OR go to HR and create/correct the employee record
- Click **Import from Excel** again to re-import, OR manually correct the **Employee** field on the line

**Step 4 – Create Payslips:**
- Once all lines are reviewed, click **"Create Payslips"**
- A confirmation dialog appears — click **Yes**
- The system:
  1. Creates one **Payroll Batch** (hr.payslip.run)
  2. Creates one **hr.payslip** for each valid employee line
  3. Injects all salary components (order earnings, bonus, petrol, deductions, fines) as payslip inputs
  4. Links each line to its payslip
- Status changes to **"Payslips Created"**

**Step 5 – Review Payslips (Optional but recommended):**
- Click **"View Payslip Batch"** to open the payroll batch
- Review individual payslips — check that salary lines computed correctly
- You can edit payslip inputs at this stage if needed
- Go back to the Salary Import when done

**Step 6 – Confirm Payslips:**
- Click **"Confirm Payslips"**
- A confirmation dialog warns this cannot be undone — click **Yes**
- The system calls `action_payslip_done()` on all payslips, which:
  1. Computes all salary rules (Basic + Order Earnings + Bonus + Petrol − Deductions − Advance − Fine = Net)
  2. Creates and posts journal entries via the accounting module
- Status changes to **"Done"**
- All payslips are now in **Done** state in the standard Payroll app

### 4.3 View Payslips After Confirmation
- Go to **Way4Tech Logistics → Payroll → Payroll Batches**
- Open the batch — you will see all payslips with their computed salary lines
- Each payslip shows: Basic, Order Earnings, Bonus, Petrol, Deductions, Net Salary

---

## 5. Commission-Based Invoicing

This module handles the scenario where your company acts as the invoicing entity on behalf of a subcontractor — collects full payment from the client, deducts commission + VAT, and transfers the balance to the subcontractor.

### 5.1 How the Commission Calculation Works

```
Full Receipt Amount                    = SAR 10,000
Commission Rate                        = 5%
Commission Amount (10,000 × 5%)        = SAR 500
VAT on Commission (500 × 15%)          = SAR 75
Total to Invoice to Subcontractor      = SAR 575     (commission + VAT)
Amount Payable to Subcontractor        = SAR 9,425   (10,000 − 575)
```

### 5.2 Step-by-Step: Record a Commission Receipt

**Step 1 – Create a Commission Receipt:**
- Go to **Way4Tech Logistics → Commission → Commission Receipts**
- Click **New**
- Fill in:
  - **Date:** Date the payment was received
  - **Customer:** The client who paid (e.g., Keeta, L&T)
  - **Subcontractor:** The partner on whose behalf you are invoicing (must be set as Vendor in Contacts)
  - **Full Receipt Amount:** Total amount received from client (including VAT)
  - **Commission %:** Default is 5% — change if different
  - **VAT %:** Default is 15% (KSA standard) — change only if applicable
  - **Period/Reference:** Free text (e.g., "March 2026" or invoice number)
  - **Journal:** Select the sales journal to use
- The system auto-calculates: Commission Amount, VAT Amount, Total to Invoice, Subcontractor Payable
- Click **Save**

**Step 2 – Confirm:**
- Click **"Confirm"**
- Status changes to **"Confirmed"**
- At this point, the record is locked for editing

**Step 3 – Create Commission Invoice:**
- Click **"Create Invoice"**
- Confirm the dialog
- The system creates a **Customer Invoice** with:
  - Line: Commission amount (pre-tax)
  - 15% VAT applied automatically
- Status changes to **"Invoiced"**
- A smart button appears to **view the invoice**

**Step 4 – Post the Invoice:**
- Click the smart button to open the invoice
- Click **"Confirm"** on the invoice to post it
- The accounting entries are created

**Step 5 – Mark Subcontractor Paid:**
- Once you transfer the subcontractor's amount, come back to the receipt
- Click **"Mark Subcontractor Paid"**
- Enter the **Payment Date** and **Payment Reference** if needed
- The receipt now shows as settled

**Step 6 – Settle:**
- Click **"Settle"** to close the record
- Status changes to **"Settled"**

---

## 6. Fleet & Truck Management

### 6.1 Add a Truck

- Go to **Way4Tech Logistics → Fleet & Trucks → Trucks**
- Click **New**
- Fill in:
  - **Truck Name/Plate:** Display name (e.g., "Truck-001" or plate number)
  - **License Plate:** Official plate number
  - **Vehicle Model / Year:** Optional details
  - **Ownership Type:**
    - **Company Owned:** Truck belongs to your branch company
    - **Investor Owned:** Truck belongs to an external investor
  - **Investor:** (Only if Investor Owned) Select the investor from Contacts
  - **Investor Profit Share %:** Percentage of net profit due to investor (default 70%)
  - **Analytic Account:** Assign an analytic account to track this truck's revenue and costs
  - **Current Client/Assignment:** Which client is this truck currently serving
- Click **Save**

### 6.2 Truck States

Use the header buttons to change the truck's operational state:

| Button | State | Meaning |
|--------|-------|---------|
| Set Active | Active | Truck is operational and generating revenue |
| Set Maintenance | Under Maintenance | Truck is off the road for repair |
| Set Inactive | Inactive | Truck is not in use |

### 6.3 Track Revenue & Costs Per Truck
- Use the **Analytic Account** assigned to each truck
- Record customer invoices and link to the truck's analytic account
- Record maintenance/repair expenses and link to the truck's analytic account
- Go to **Accounting → Reporting → Analytic Report** to see P&L per truck

---

## 7. Investor Profit Payables

At the end of each month (or agreed period), calculate the profit share owed to each investor.

### 7.1 Step-by-Step: Create an Investor Payable

**Step 1 – Create the Payable Record:**
- Go to **Way4Tech Logistics → Fleet & Trucks → Investor Payables**
- Click **New**
- Fill in:
  - **Truck:** Select the investor-owned truck
  - **Investor:** Auto-filled from the truck record
  - **Period Start / End:** The month being calculated (e.g., 01/03/2026 – 31/03/2026)
  - **Total Revenue from Client:** Total income earned by this truck this period
  - **Total Maintenance/Expenses:** All costs incurred for this truck this period
- The system auto-calculates:
  - **Net Profit** = Revenue − Expenses
  - **Investor Share %** = pulled from the truck record
  - **Amount Due to Investor** = Net Profit × Investor Share %
  - **Company Net** = Net Profit − Investor Amount

**Step 2 – Confirm:**
- Review the amounts
- Click **"Confirm"**
- Status changes to **"Confirmed"**

**Step 3 – Create Vendor Bill:**
- Click **"Create Vendor Bill"**
- The system creates a **Vendor Bill** for the investor with:
  - Line: "Investor Profit Share – [reference]"
  - Amount = investor_amount
- A smart button shows the linked bill

**Step 4 – Post & Pay the Bill:**
- Open the vendor bill via the smart button
- Click **"Confirm"** to post it
- Process payment through normal Odoo payment workflow

**Step 5 – Mark as Paid:**
- Return to the Investor Payable record
- Click **"Mark as Paid"**
- Status changes to **"Paid"** with today's date recorded

---

## 8. Employee Additional Costs (KSA)

Track mandatory and statutory costs per employee per month for accurate profitability reporting.

### 8.1 KSA Cost Components

| Cost | Description |
|------|-------------|
| **GOSI** | Social Insurance contribution (company portion, typically 10% of salary) |
| **Iqama** | Residency permit renewal cost |
| **Medical Insurance** | Company-paid health insurance premium |
| **Saudization (Nitaqat)** | Cost related to Saudization compliance levy or replacement |
| **Other Costs** | Any additional overhead (uniforms, equipment, etc.) |

### 8.2 Step-by-Step: Record Employee Costs

**Step 1 – Create Cost Record:**
- Go to **Way4Tech Logistics → Payroll → Employee Costs**
- Click **New**
- Fill in:
  - **Employee:** Select the employee
  - **Employee Type:** Permanent Employee or Freelancer
  - **Period Start / End:** The month this covers
  - **Assigned Client:** The client this employee is deployed to (for profitability)
  - **Analytic Account:** For cost allocation in analytic reports
  - **Cost Components:** Enter amounts for GOSI, Iqama, Insurance, Saudization, Other
- **Total Monthly Cost** is auto-calculated

**Step 2 – Confirm:**
- Click **"Confirm"**
- Status changes to **"Confirmed"**
- Record is locked

### 8.3 Use for Profitability Analysis
- Filter by **Client** to see total employee costs deployed per client
- Filter by **Employee** for individual cost history
- Use **Analytic Accounts** to pull costs into the P&L report per client/project

---

## 9. Manpower Billing Contracts

Manage contracts where you supply manpower to clients and bill them — either a fixed monthly amount or based on actual hours worked.

### 9.1 Two Billing Types

| Type | When to Use |
|------|-------------|
| **Fixed Price** | Monthly fixed fee regardless of hours — common for food delivery platforms |
| **Hourly Rate** | Bill per hour worked — common for construction/industrial projects |

### 9.2 Step-by-Step: Create a Manpower Contract

**Step 1 – Create the Contract:**
- Go to **Way4Tech Logistics → Manpower → Manpower Contracts**
- Click **New**
- Fill in:
  - **Contract Name:** Descriptive name (e.g., "L&T – Manpower Q1 2026")
  - **Client:** The company you are supplying manpower to
  - **Contract Type:** Food Delivery or Project Based
  - **Billing Type:** Fixed Price or Hourly Rate
  - **Fixed Monthly Amount** (if Fixed) OR **Hourly Rate** (if Hourly)
  - **Start Date / End Date:** Contract period
  - **Analytic Account:** For revenue tracking per client/project
- Click **Save**

**Step 2 – Add Manpower (Manpower tab):**
- In the **Manpower** tab, click **Add a line**
- For each person assigned:
  - **Employee Type:** Permanent or Freelancer
  - **Employee:** Select from HR employees (for Permanent)
  - **Freelancer/Vendor:** Select the vendor contact (for Freelancer)
  - **Role/Position:** e.g., "Driver", "Laborer", "Supervisor"
  - **Start Date / End Date**
  - **Daily Cost:** Cost of deploying this person per day (for your internal costing)

**Step 3 – Activate the Contract:**
- Click **"Activate"**
- Status changes to **"Active"**

**Step 4A – For Hourly Contracts: Log Timesheets:**
- In the **Timesheets** tab, click **Add a line** for each timesheet entry:
  - **Date:** Work date
  - **Employee:** Who worked
  - **Description:** What was done
  - **Hours Worked:** Number of hours
  - Tick **Approved** once hours are verified with the client
- **Total Hours** is auto-calculated from all timesheet lines

**Step 4B – For Fixed Price Contracts:**
- No timesheets needed — the fixed amount is used directly for invoicing

**Step 5 – Generate Invoice:**
- Click **"Create Invoice"**
- For **Fixed Price:** Invoice is created with the fixed monthly amount
- For **Hourly:** Invoice is created with Total Hours × Hourly Rate
- The invoice is linked to the contract and visible via the smart button
- Go to the invoice (smart button) to review, confirm, and send to client

**Step 6 – Complete or Cancel:**
- At contract end, click **"Complete"** → status = Completed
- If cancelled early, click **"Cancel"** → status = Cancelled
- To reopen a cancelled contract: **"Reset to Draft"**

---

## 10. Configuration

### 10.1 Salary Structures
- Go to **Way4Tech Logistics → Configuration → Salary Structures**
- The **"Rider Payroll" (RIDER)** structure is pre-configured
- You can add additional structures for different rider types or salary models

### 10.2 Salary Rules
- Go to **Way4Tech Logistics → Configuration → Salary Rules**
- The 8 Rider rules are pre-configured:

| Rule | Code | Computes |
|------|------|---------|
| Basic Salary | RIDER_BASIC | `contract.wage` |
| Order Earnings | RIDER_ORDER | From input `ORDER_EARN` |
| Bonus | RIDER_BONUS_RULE | From input `RIDER_BONUS` |
| Petrol Allowance | RIDER_PETROL_RULE | From input `RIDER_PETROL` |
| Deduction | RIDER_DED_RULE | `-(RIDER_DED input)` |
| Advance Deduction | RIDER_ADV_DED_RULE | `-(RIDER_ADV_DED input)` |
| Fine | RIDER_FINE_RULE | `-(RIDER_FINE input)` |
| Net Salary | RIDER_NET | Earnings − Deductions |

### 10.3 Multi-Company Setup
- Each company/branch in Odoo is set up separately under **Settings → Companies**
- When creating Salary Imports, Employee Costs, or Contracts — the **Company** field determines which branch the record belongs to
- Users can switch between companies using the company selector in the top-right corner

---

## 11. Excel Template Reference

### Rider Salary Import Template

Save as `.xlsx` format. Row 1 = headers (exact names not required, just column position matters).

```
Column A  →  Employee Name          (text, must match Odoo HR employee name)
Column B  →  Rider Type             (text: "employee" or "freelancer")
Column C  →  Fixed Salary           (number, e.g. 1500)
Column D  →  Order Earnings         (number, e.g. 800)
Column E  →  Bonus                  (number, e.g. 200)
Column F  →  Petrol                 (number, e.g. 100)
Column G  →  Deduction              (number, e.g. 50)
Column H  →  Advance Deduction      (number, e.g. 250)
Column I  →  Fine                   (number, e.g. 0)
Column J  →  Notes                  (text, optional)
```

**Tips:**
- Empty cells are treated as 0
- Employee names are matched using a partial/case-insensitive search
- If two employees have similar names, use the most unique part of the name
- Save the file as `.xlsx` (Excel 2007+), NOT `.xls` or `.csv`

---

## 12. Status Reference (All Workflows)

### Salary Import
```
Draft → [Import Excel] → Imported → [Create Payslips] → Payslips Created → [Confirm Payslips] → Done
```

### Commission Receipt
```
Draft → [Confirm] → Confirmed → [Create Invoice] → Invoiced → [Mark Sub Paid] → [Settle] → Settled
```

### Investor Payable
```
Draft → [Confirm] → Confirmed → [Create Vendor Bill] → [Mark as Paid] → Paid
```

### Employee Cost
```
Draft → [Confirm] → Confirmed
```

### Manpower Contract
```
Draft → [Activate] → Active → [Complete] → Completed
                            → [Cancel]   → Cancelled → [Reset to Draft] → Draft
```

### Truck State
```
Active ↔ Under Maintenance ↔ Inactive  (can switch freely using header buttons)
```

---

## 13. Common Errors & Fixes

| Error | Cause | Fix |
|-------|-------|-----|
| "Employee not found: [Name]" | Employee name in Excel doesn't match Odoo | Fix the name in Excel to match the HR employee record, or create the employee in HR first |
| "No active contract found" | Employee exists but has no open contract | Go to Payroll → Employees → Contracts, open the employee's contract and set its state to "Running/Open" |
| "openpyxl not installed" | Python library missing | Run `pip install openpyxl` inside the Docker container and restart |
| Commission invoice not creating | Subcontractor not set as vendor | Open the subcontractor in Contacts, tick "Is a Vendor" checkbox |
| Payslip amounts wrong | Salary structure not assigned to contract | Open the employee's contract and set Salary Structure = "Rider Payroll" |
| Module not appearing in home screen | Groups not assigned | Go to Settings → Users → open user → add to "Logistics / User" group |
| Investor payable bill not creating | Investor not set on truck | Open the truck, set the Investor field, and confirm ownership type = "Investor Owned" |

---

## Quick Reference Card

| Task | Where to Go |
|------|------------|
| Import monthly rider salaries | Payroll → Salary Imports → New |
| Check payslip batch | Payroll → Payroll Batches |
| Record GOSI/Iqama costs | Payroll → Employee Costs → New |
| Record a client receipt + commission | Commission → Commission Receipts → New |
| Add a new truck | Fleet & Trucks → Trucks → New |
| Calculate investor profit share | Fleet & Trucks → Investor Payables → New |
| Add a manpower client contract | Manpower → Manpower Contracts → New |
| Log timesheet hours | Manpower Contracts → [open contract] → Timesheets tab |
| Generate client invoice from contract | Manpower Contracts → [open contract] → Create Invoice button |
| View salary rules | Configuration → Salary Rules |

---

*Guide version: 1.0 | Module version: 19.0.1.0.0 | Way4Tech*
