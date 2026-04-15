# BRD v1.0 — Alzain Tower Contracting Est
**Client:** AlZain Tower Contracting Est, Saudi Arabia
**Project:** Odoo ERP Implementation
**Odoo Version:** Odoo 19 (Community + Enterprise)
**Prepared Date:** 15-01-2026
**Document Version:** v1.0
**Archive source:** First BRD received from client (preceded Quote v1)

---

## 1. Introduction

This document defines the business requirements and functional expectations for implementing Odoo ERP across a multi-branch organization engaged in logistics, manpower supply, and commission-based financial operations. The objective of this document is to map existing business processes into Odoo modules, identify standard functionalities versus customization needs, and establish a clear implementation scope. The proposed Odoo solution aims to centralize branch-wise operations, streamline workforce and fleet management, ensure accurate invoicing and commission handling, and provide real-time financial visibility to management and stakeholders.

## 2. Client Business Overview

The client operates multiple branch companies, such as logistics and manpower supply entities, each functioning as an operational and financial unit. These branches manage owned truck fleets as well as investor-owned trucks, which are rented out to external clients. The business is responsible for tracking fleet revenues, repair and maintenance costs, and distributing profits to investors on a monthly or yearly basis.

In addition to logistics operations, the branch companies supply manpower to food delivery partners and project-based clients. The workforce includes both permanent employees and freelancers. Permanent employees are hired under company sponsorship and incur statutory and operational costs such as visa, iqama, insurance, GOSI, and Saudization, while freelancers are engaged on a temporary or daily basis with only salary-related costs. Profitability is tracked per client, particularly for food delivery partners.

The organization also supplies manpower to various external companies for their projects, where deployment may include permanent or freelance resources and, in some cases, trucks. Billing models vary by client and may be based on fixed rates or hourly usage. Furthermore, the business provides commission-based invoicing services to partner companies, wherein client payments are received into the branch company's bank accounts and settled back after deducting an agreed commission percentage along with applicable VAT. The branches are also responsible for providing accounting and financial reports on a daily, monthly, and yearly basis to ensure transparency and compliance.

## 3. Business Structure

### 3.1 Company & Branch Setup

- One Parent Company
- Multiple Branch Companies (e.g., Woodpecker Logistics, Future Power Trading, Fame Island Contracting)
- Each branch:
  - Has its own customers, projects, employees, freelancers, and fleets
  - Maintains independent profitability
  - Shares common accounting rules, VAT, and reporting standards

In Odoo, this is mapped using:

- Multi-Company Setup
- Shared Chart of Accounts with company-specific journals

## 4. Transportation & Truck Fleet Business Mapping

### 4.1 Business Scenario

- Branch companies own some trucks
- Some trucks are provided by external investors
- Trucks are rented to client companies/projects
- Investors receive monthly/yearly profit share
- Repair and maintenance costs are managed by branch companies

### 4.2 Odoo Mapping

**Master Data**
- Trucks configured as Assets / Fleet Vehicles
- Investors Truck on contract configure
- Investors configured as Partners
- Ownership type identified using custom fields (Own / Investor)

**Operations**
- Trip or rental-based usage tracked per truck
- Maintenance logs recorded per vehicle

**Accounting**
- Revenue recorded per truck and per customer
- Maintenance and repair expenses allocated to respective truck
- Investor payable created based on agreed profit-sharing logic

**Reporting**
- Truck-wise profitability
- Investor receivable & aging reports (Truck wise profitability of investor trucks + related customer / vendor report with aging)
- Customer-wise profitability (Create the limit check regarding the rental revenue of each truck against issuance of each PO from customer)

**Odoo Modules Used**
- Fleet Management
- Accounting
- Analytic Accounting
- Custom Investor Profit Report

## 5. Manpower Supply Business Mapping

### 5.1 Business Scenarios

**A. Food Delivery Manpower**

- Riders supplied to food delivery companies (Keeta, Hunger, Chefz)
- Two manpower types:
  - Own Employees (Company visa)
  - Freelancers (Daily / salary-based)

**Own Employee Costs:**
- Salary
- Iqama
- Insurance
- GOSI
- Saudization

**Freelancer Costs:**
- Fixed daily or monthly cost

Profitability tracked per food delivery partner.

**B. Project-Based Manpower Supply**

- Manpower supplied to construction & industrial projects (L&T, Arass II, Khushabiya, etc.)
- Pricing models:
  - Fixed cost
  - Hourly cost (based on client timesheets)
- Freelancers are temporary
- Own manpower is permanent

### 5.2 Odoo Mapping

**HR Structure**
- Employees configured for permanent staff
- Freelancers configured as Vendors

**Attendance & Timesheets**
- Timesheets recorded based on client-provided data
- Hourly cost calculation automated

**Payroll & Costing**
- Payroll for own employees
- Vendor bills for freelancers
- Cost allocation per project/customer

**Invoicing**
- Customer invoices generated based on:
  - Hours × Rate
  - Fixed project cost

**Odoo Modules Used**
- Employees
- Timesheets
- Payroll
- Accounting
- Projects
- Analytic Accounting

## 6. Commission-Based Invoicing Model

### 6.1 Business Scenario

- Any third person (Called him subcontractor) doing own business just using name of our Parent Company or Branch company.
- We make the invoice on behalf of subcontractor with name of company as registered by him in our system.
- We charged 5% commission on invoice value on cash basis and deduct the VAT amount.

### 6.2 Odoo Mapping

**Accounting Flow**

1. Full customer payment received
2. Revenue recorded as liability (payable to subcontractor after deducting VAT amount and 5% commission)
3. Commission invoice generated: `(Invoice Amount – VAT) × Commission %`
4. VAT applied on commission

**Reporting**
- Daily / monthly / yearly commission reports
- VAT reports
- Client receivable & payable reports
- Payment tracking payment made or payable to subcontractor

**Odoo Modules Used**
- Accounting
- Invoicing
- VAT Reports
- Custom Commission Logic

## 7. Profitability & Reporting Structure

Profitability is tracked at multiple levels:

- Branch-wise
- Customer-wise
- Project-wise
- Truck-wise
- Investor-wise

**Key Reports:**
- P&L per branch
- Customer profitability
- Investor aging report
- Employee cost report
- VAT return report
- Cash Statement

Implemented using:
- Analytic Accounts
- Analytic Tags
- Custom Financial Reports

## 8. Compliance & Controls

- VAT compliance per branch
- GOSI & Saudization cost tracking
- Audit-ready accounting structure
- Role-based access per company and department

## 9. End-to-End Odoo Process Flow

1. Company & Branch setup
2. Master data creation (customers, employees, fleets)
3. Operational data entry (timesheets, maintenance)
4. Cost & revenue allocation
5. Automated invoicing
6. Accounting & VAT posting
7. Profitability analysis
8. Management reporting

## 10. Conclusion

This Odoo Business Requirement Mapping ensures that all operational, financial, and compliance requirements of the client are accurately represented within Odoo. The solution is scalable, audit-ready, and provides real-time visibility into profitability and performance across branches, projects, and investments.

---

## Quote v1 — Way4Tech response to this BRD

**Total project cost:** SAR 3,700
**Timeline:** 3–4 weeks
**Payment terms:** 50% on confirmation / 30% on UAT / 20% on deployment

### Phase 1 — Core System Setup (Standard Configuration)

**Multi-Company & Branch Structure**
- Parent company with multiple operational branches
- Separate customers, vendors, employees, and fleets per branch
- Shared chart of accounts with branch-wise reporting

**Accounting & VAT (KSA)**
- VAT configuration and tax reports
- Customer invoicing and vendor billing
- Branch-wise P&L and cash reporting
- Analytic accounts for customer and project profitability

**Manpower Management**
- Employee records for company-sponsored staff
- Vendor setup for freelancers
- Cost tracking for salaries, GOSI, insurance, iqama, and other overheads

**Fleet Cost Tracking (Financial View)**
- Expense allocation per truck
- Revenue tracking per customer/project
- Investor payable tracking (financial side)

### Phase 2 — Custom Development

**Rider Payroll Automation (HungerStation / Delivery Riders)**
- Import rider salary sheets from Excel
- Data validation and error control during import
- Automatic classification: Company riders → Payslip; Freelancers → Vendor bill
- Handling of: fixed salary, order-based earnings, bonuses, deductions, petrol, advances, fines
- Net payable calculation per rider
- Analytic tagging per client (e.g., HungerStation)
- Accounting entries posted automatically

**Commission-Based Invoicing Module**
- Recording of full customer receipts as liability
- Automatic commission calculation (percentage after VAT)
- Commission invoice generation
- Payable balance tracking for subcontractors
- VAT applied only on commission portion
- Commission reporting (daily / monthly / yearly)

**Profitability & Reporting Enhancements**
- Branch-wise profitability
- Customer / project profitability
- Rider cost vs revenue analysis
- Investor payable and aging report
- Custom financial views using analytic accounts

### Exclusions (not included in Quote v1)

- Odoo Enterprise licenses
- HR payroll localization for full Saudi legal compliance
- Mobile applications or third-party API integrations
- Hosting and server management
- Ongoing AMC / support contracts

### Support

A post-go-live support period of 15 days is included for issue resolution and minor adjustments. Any additional enhancements will be handled through a separate change request.
