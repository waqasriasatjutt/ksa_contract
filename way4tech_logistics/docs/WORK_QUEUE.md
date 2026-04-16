# Work Queue — Pending Tasks & Open Questions
**Project:** way4tech_logistics for Alzain Towers / Woodpecker
**Purpose:** Authoritative list of pending work and blocked items. Next session (human or AI) should read this first to know exactly what's ready to execute, what's waiting on client answers, and what decisions are still pending.

**Last updated:** 2026-04-16 — Sessions to date:
- Session 1: Initial module buildout (Quote v1 scope) — 100% delivered
- Session 2: BRD v2 feedback — 7 items quoted as CR-1 (SAR 3,500), ~70% delivered
- Session 3: BRD v3 feedback — 17 items quoted as CR-2 (SAR 8,500), ~25% delivered
- Session 4 (current): 11 items completed from client's latest feedback list — now 17/23 done (74%)

**Latest client-facing message sent:** Quote v1 delivery notice + payment request (short version, 2-line)

**Current state against the last feedback list (23 items):**
- ✅ 17 done (74%)
- ❌ 3 remaining (can do without client input)
- 🔴 2 blocked on client answers
- ⚠️ 1 out of scope (core HR)

---

## How to use this file

1. **When client sends an answer to an open question** → find the question below, update the "Client Answer" field, move related tasks from 🟡 Blocked → 🟢 Ready, and start executing.
2. **When client sends a new requirement** → add it under Section 3 or Section 4, and update `PROJECT_TRACKING.md` Section 3 (Requirement Matrix).
3. **When a task is completed** → remove from pending list, mark ✅ in `PROJECT_TRACKING.md` Section 4.
4. **For AI sessions:** Before doing anything, read:
   - This file (`docs/WORK_QUEUE.md`) — what's pending and what's blocked
   - `PROJECT_TRACKING.md` — full project state + billing
   - Relevant BRD archives in `docs/brd_v{N}_alzain.md`

---

## Section 1 — Tier A: Ready to execute NOW (no client input needed)

| # | Task | Est. | Implementation notes | Status |
|---|---|---|---|---|
| A1 | **PO Renewal workflow** | 1.5h | Add "Renew / Extend PO" button on `way4tech.client.po` form. Wizard asks: (a) add value to same PO, or (b) create new linked PO. Field: `parent_po_id` (M2O self) + `renewal_child_ids` (O2M self). Trigger from state `near_limit` or `closed`. Update `_compute_balance` so children sum with parent. | ⏳ Pending |
| A2 | **Repeated repair detection** | 1h | In `wizard/maintenance_history_wizard.py`, group by `way4tech_maint_type` per vehicle and flag any category recurring within N days (default 60). Add "Repeat Alert" column + filter "Show only repeats". | ⏳ Pending |
| A3 | **Previous Expense Display widget** | 1.5h | Field `way4tech_prev_expense_id` already exists on `account_move_extension.py`. Compute: search `account.move.line` matching `partner_id + analytic_distribution` or vehicle — take last posted one before current date. Show inline on account.move form as `<div class="text-muted">`. | ⏳ Pending |
| A4 | **Office Staff Cost Breakdown fields** | 2h | On `way4tech.employee.cost`, add `sim_cost`, `car_maintenance_cost`, `fuel_cost`, `fat_cost`. Update `total_cost` compute. Update `wizard/staff_cost_report_wizard.py` + report template. | ⏳ Pending |
| A5 | **Invoice Category admin control per user** | 1h | Add `allowed_group_ids = Many2many('res.groups')` on `way4tech.entry.category`. In `action_post`, filter by allowed groups. | ⏳ Pending |
| A6 | **Bill-level access restriction** | 1h | Create `ir.rule` on `account.move` with domain `[('way4tech_category_id.restricted', '=', False)]` for non-managers. Add `restricted = Boolean` field to `way4tech.entry.category`. | ⏳ Pending |
| A7 | ~~Hide indirect expenses for investor-owned trucks~~ | 15m | **Resolved via info banner (Decision Log 2026-04-15).** Info banner explains company bears from 50% share. Can revisit if client answers Q9 differently. | ✅ Done (banner) |

**Total Tier A remaining: ~7 hours, closes 6 items**

---

## Section 2 — Tier B: Medium tasks (doable without client input)

| # | Task | Est. | Implementation notes | Status |
|---|---|---|---|---|
| B1 | **Asset depreciation SL/DB compute** | 4h | Complete `asset_register.py`. Add `depreciation_method` selection, `useful_life_years`, `residual_value`. Build `_compute_depreciation_schedule` O2M + cron for monthly posting. **May switch to `om_account_asset` based on Q4.** | ⏳ Pending |
| B2 | **ZIP bundle report download** | 4h | Wizard `way4tech.report.zip.wizard`: takes report_ref + record_ids, renders PDF, collects all `ir.attachment`, zips into single BytesIO + returns as binary download. | ⏳ Pending |
| B3 | **Daily Cashflow Alert — Email delivery only** | 3h | Complete `cashflow_alert.py::_cron_send_alert`. Render QWeb template (cash, bank, AR, AP, top 5 overdue). Use matplotlib for chart PNG. Send via `mail.mail`. **Skip WhatsApp until Q3.** | ⏳ Pending |
| B4 | **Fleet Excel Export** | 2h | `way4tech.fleet.excel.export` wizard — 29-column xlsx download. | ✅ **Done 2026-04-16** — `wizard/fleet_excel_export.py` + views |
| B5 | **Fleet Excel Import** | 3h | `way4tech.fleet.excel.import` wizard — parse xlsx, create/update fleet.vehicle. Auto-create vendors, plate dedup warnings. | ⏳ Pending |
| B6 | **Trip Excel Export + Import** | 4h | `way4tech.truck.trip` — truck plate, client, date, trip_type, rental_type + revenue/cost. Import → draft state. | ⏳ Pending |
| B7 | **Maintenance Excel Export + Import** | 3h | `fleet.vehicle.log.services` import + export wizards. | ✅ **Done 2026-04-16** — `wizard/maintenance_excel_wizard.py` + views (both import and export in one file) |
| B8 | **Fleet PDF report (QWeb)** | 2h | QWeb template with all fleet master data + conditional installment/operation card blocks. | ✅ **Done 2026-04-16** — `views/report_fleet_data.xml` |
| B9 | **Graph view on existing reports** | 3h | Add `<graph>` + `<pivot>` to truck_profitability, salesperson_profitability, employee_margin, investor_aging, staff_cost, maintenance_history. | ⏳ Pending |

**Total Tier B remaining: ~21 hours** (was 28h, done 7h)

---

## Section 3 — Tier C: Larger features

| # | Task | Est. | Implementation notes |
|---|---|---|---|
| C1 | **Inventory for Fleet Parts** | 5h | (1) Add `stock` to manifest depends. (2) Create product categories: `Tyres`, `Oil`, `Batteries`, `Spare Parts` in data file. (3) Add `parts_consumed_ids = One2many('stock.move.line')` on `fleet.vehicle.log.services` — each maintenance record links to the stock moves of parts consumed. (4) Add button "Consume Parts" that opens a wizard to pick products + qty, creates `stock.move.line` records, decrements stock. (5) Add cost from parts to maintenance `amount` automatically. (6) New report: stock consumption per vehicle per period. |
| C2 | **Driver Payroll Excel import (Basic+Wages, Basic+Hourly)** | 4h | Extend `salary_import_line.py` with `salary_template = Selection([('rider', 'Delivery Rider'), ('basic_wages', 'Basic + Wages'), ('basic_hourly', 'Basic + Hourly')])`. Update compute logic per template. Add new columns to `salary_excel_import` for hourly/wages fields. **Rider template unchanged** — this is additive, not replacement. |
| C3 | **Salesperson Commission Engine** | 6-8h | **BLOCKED — Q2 to client.** Will be a new model `way4tech.commission.rule` with criteria selection (fixed/sale%/gross%/net%), then refactor `truck_trip.salesperson_id` from `Many2one('res.users')` → `Many2many('hr.employee')` through a junction model `trip.salesperson.line` that carries the commission amount per salesperson. Design needs client input before build. |

**Total Tier C: ~15-17 hours (C3 blocked)**

---

## Section 4 — Open Questions to Client (blockers)

### 🔴 Must answer before we can continue related work

#### Q1 — "Trip revenue type is mix" clarification
**Asked:** 2026-04-16
**Client answer:** *(pending)*
**Blocks:** Nothing directly, but we can't fix what we don't understand.
**Related task:** None specific — likely a UI fix once we know what's wrong.
**Question sent:**
> You wrote "Trip revenue type is mix". We currently show two fields: Trip/Revenue Type (Delivery/Rental/Flatbed/Middleman/...) and Revenue Basis (Manual/Hours/Per Trip/Flat). Are these confusing? Should we (a) merge them, (b) rename one, or (c) hide one by default? A screenshot would help.

#### Q2 — Salesperson Commission rules
**Asked:** 2026-04-16
**Client answer:** *(pending)*
**Blocks:** C3 (Commission Engine build)
**Question sent:**
> For 4 commission criteria + multi-salesperson:
> (a) Can one salesperson have multiple rules stacked? (50 SAR fixed + 2% of sale)
> (b) How is commission split between multiple salespersons? (equal / custom % / each gets own rate)
> (c) When is commission calculated? (invoice post / payment received / monthly batch)
> (d) Where should it post? (auto vendor bill / report only)
> (e) Salesperson = `res.users` or `hr.employee`? You said prefer employee — confirm?

#### Q3 — WhatsApp provider
**Asked:** 2026-04-16
**Client answer:** *(pending)*
**Blocks:** Full delivery of B3 (cashflow alerts), and any "auto-send via WhatsApp" feature.
**Workaround:** Build email-only version now, add WhatsApp after client responds.
**Question sent:**
> Do you have a WhatsApp Business API account (Meta direct, Twilio, 360Dialog, UltraMsg)? If yes, share credentials. If no, we'll ship Email-only for now and add WhatsApp in a follow-up phase.

### 🟡 Good to have (affects implementation approach, not urgent)

#### Q4 — Asset Depreciation approach
**Asked:** 2026-04-16
**Client answer:** *(pending)*
**Blocks:** B1 (can start custom version without answer, but wasted work if they pick `om_account_asset`)
**Question sent:**
> For depreciation: (a) activate community `om_account_asset` (ready-made, free), or (b) build custom engine inside way4tech_logistics (more integrated, +3-4 hours dev)?

#### Q5 — Office Staff Cost — manual fields vs computed
**Asked:** 2026-04-16
**Client answer:** *(pending)*
**Blocks:** A4 (can start with approach (a) manual fields as default and switch if needed)
**Question sent:**
> Should (SIM + car + fuel + FAT) be (a) new manual fields, or (b) computed automatically from existing records via category tagging?

#### Q6 — Excel templates — existing format or new
**Asked:** 2026-04-16
**Client answer:** *(pending)*
**Blocks:** B5, B6, B7, C2 (can start with standardized Odoo template, rework if client wants their format)
**Question sent:**
> You mentioned sharing separate Excel sheets for salary structure. For the import feature, should we (a) use your exact existing format — please share the files, or (b) create a new standardized template?

#### Q7 — Previous Expense Display matching logic
**Asked:** 2026-04-16
**Client answer:** *(pending)*
**Blocks:** A3 (can build with default interpretation, adjust if different)
**Default assumption:** Match by (vehicle + maintenance type) for fleet entries, (vendor + category) for others.
**Question sent:**
> For "show previous related expense", match by: (a) same vendor + same category, (b) same vehicle + same maintenance type, or (c) same product + same partner? BRD example was "oil change for truck #6280" which implies (b).

#### Q8 — Employee Category Report auto-send trigger
**Asked:** 2026-04-16
**Client answer:** *(pending)*
**Blocks:** Employee category auto-send feature.
**Question sent:**
> (a) Auto monthly on 1st, (b) manual button only, or (c) both? Recipient: employee themselves, HR admin, or both?

#### Q9 — Indirect expenses visibility for investor trucks
**Asked:** 2026-04-16
**Client answer:** *(pending)*
**Blocks:** A7 (small — can change in 15 min either way)
**Current state:** Visible with info banner explaining company bears them.
**Question sent:**
> For investor-owned profitability, indirect expenses: (a) keep visible with banner (current), (b) hide completely from form, or (c) move to admin-only section?

### 🟢 Nice to have (non-blocking)

#### Q10 — Print badge ID error details
**Asked:** 2026-04-16
**Client answer:** *(pending)*
**Blocks:** Nothing — core HR issue, separate investigation.

#### Q11 — Fleet Model vehicle types — any additional needed?
**Asked:** 2026-04-16
**Current:** Car, Bike, Truck, Bus/Minibus, Flatbed, Trailer, Heavy, Other
**Client answer:** *(pending)*

#### Q12 — PO per-category rates
**Asked:** 2026-04-16
**Client answer:** *(pending)*
**Blocks:** PO per-category rates feature (from earlier BRD)
**Question sent:**
> (a) Rate unit — always hourly, or also per day/trip/month? (b) Category linked to vehicle type or service type? (c) Should invoicing auto-pick the rate by what's being billed?

---

## Section 5 — Decision Log

Record of decisions already made so future sessions don't re-open settled questions.

| Date | Decision | Why |
|---|---|---|
| 2026-04-15 | Indirect expenses stay visible with info banner (not hidden) for investor trucks | Matches BRD formula: "borne by company from its 50% share". Hiding entirely would obscure the compute logic. User may override via Q9 answer. |
| 2026-04-15 | `investor_share_basis` defaults to `gross` | Matches original BRD v2 formula. Client can toggle to `net` per record. |
| 2026-04-15 | Partner CR/Iqama moved to new notebook tab "KSA Info" | Client feedback said "make new tab" — interpreted literally. |
| 2026-04-15 | Driver iqama shown on trip as read-only related field | User can click into driver to edit if needed. |
| 2026-04-15 | Installment payment = vendor bill (not raw journal entry) | Proper Odoo accounting — enables `Register Payment` standard flow. |
| 2026-04-15 | Investor bill = `in_invoice` (not raw journal entry) | Same reason. |
| 2026-04-15 | PO balance reads from actual posted invoices (fallback to trip revenue for uninvoiced trips) | More accurate than just summing trip.revenue. |
| 2026-04-15 | Entry category enforcement is hard-block, not auto-assign | Prevents silent mis-categorization. Only enforced for logistics users. |
| 2026-04-15 | Mandatory entry category skipped if no categories exist in DB | Allows fresh install without blocking. |
| 2026-04-16 | Fleet sequence = simple 10-digit (no prefix) starting at 1000000001 | Client explicitly requested. Applied via direct DB update (file is noupdate=1). |
| 2026-04-16 | Fleet vehicle_type extended: +Truck, Bus, Flatbed, Trailer, Heavy, Other | Client asked for more than Car/Bike. Used `selection_add` with `ondelete='set default'`. |
| 2026-04-16 | Vehicle Models admin menu added under Logistics → Configuration → Vehicle Models | Uses core `fleet.fleet_vehicle_model_action` — no new action needed. |
| 2026-04-16 | Quote v1 declared 100% delivered | All items in original SAR 3,700 scope are built and working. |
| 2026-04-16 | Fleet PDF Report implemented as binding_type=report on fleet.vehicle | Accessible from vehicle form → Print dropdown. |
| 2026-04-16 | Fleet Excel Export — full-dataset export (no filters) | Simple first version; can add filters later if requested. |
| 2026-04-16 | Maintenance Excel Import/Export in single file `maintenance_excel_wizard.py` | Two models in one Python file to keep related wizards together. |
| 2026-04-16 | Maintenance Import: 6 columns (Date, Plate, Category, Vendor, Amount, Notes) | Minimum required fields; case-insensitive category lookup; auto-creates missing vendors with supplier_rank=1. |
| 2026-04-16 | Maintenance Import creates records in `draft` state | User must review and confirm — safer than auto-confirming imported data. |
| 2026-04-16 | Payment request message to client = 2-line short version | Client asked for short, no amounts, no details. Just completion + polite payment ask. |
| 2026-04-16 | CR-1 ~70% delivered, CR-2 ~30% delivered | Significant work done ahead of formal approval. Client should sign CR-1 and CR-2 before additional work. |

---

## Section 6 — Known Free Extras (beyond any quote)

These are in the module but NOT in any BRD or quote. They should be acknowledged when negotiating — client is getting value for free. Do NOT re-quote them as "new".

### Architectural / UX improvements (Session 1-3)
1. Vendor bill flow for installments (vs raw JE)
2. Investor bill as `in_invoice` with reconciliation
3. PO balance uses actual posted invoices
4. Hide investor fields on company-owned profitability
5. Cron filters investor-only trucks for monthly auto-generate
6. License plate auto-sync across trip + profitability views
7. Entry category hard-block on post (mandatory gate)
8. Way4Tech fleet sequence generator
9. View binding fixes (custom forms for fleet.vehicle + fleet.vehicle.log.services)
10. Maintenance smart button → custom action

### Quick wins (Session 4 — 2026-04-16)
11. Auto-select current driver on trip (onchange from current_driver_assignment_id)
12. Driver iqama read-only on trip form (related field)
13. Partner CR/Iqama proper notebook tab "KSA Info"
14. Maintenance scan copy binary field with filename widget
15. Vehicle model edit/delete config menu
16. Vehicle type extended selection (Truck/Bus/Flatbed/Trailer/Heavy/Other)
17. Indirect expenses info banner for investor trucks

### Excel + PDF (Session 4 — 2026-04-16)
18. Fleet PDF Report with conditional sections (installment/operation card)
19. Fleet Excel Export with 29 columns and styled headers
20. Maintenance Excel Export with date/vehicle filters
21. Maintenance Excel Import with auto-vendor creation and per-row error logging

**Estimated free value:** ~30-35 hours of work (~SAR 9,000-10,500 at standard rate)

---

## Section 7 — Protocol for Next Session

When you return to this project, read in this order:

1. **This file (`WORK_QUEUE.md`)** — what's pending, what's blocked, what decisions were made
2. **`PROJECT_TRACKING.md`** — full project state, requirement matrix, billing summary
3. **`docs/brd_v1_alzain.md` / `brd_v2_alzain.md` / `brd_v3_alzain.md`** — source requirement documents
4. **Latest user message** — what's the immediate ask?

### Decision tree for new client input

```
Client sends something new
         ↓
    What type?
         ↓
  ┌──────┼──────┬────────────┬──────────────┐
  │      │      │            │              │
Answer  New   Bug fix    Clarification   Scope
to Q?   req?  request   on existing      change?
  │      │      │            │              │
  ↓      ↓      ↓            ↓              ↓
Update  Add to Fix +       Update        Add to
Section Section verify     Section 5     Tracking
4       3 or 4                           Section 3
move                                     + CR-N
Tier to                                  quote
Ready                                    
```

### When executing Tier A/B/C tasks

1. Read the task notes from the relevant section here
2. Check `PROJECT_TRACKING.md` Section 3 to confirm it's still valid scope
3. Check `PROJECT_TRACKING.md` Section 4 for what's already built (avoid duplicating)
4. Execute. Update the module.
5. Run `docker exec odoo19 odoo -d odoo19 --db_host db --db_user odoo --db_password odoo -u way4tech_logistics --stop-after-init` then `docker restart odoo19`
6. Update both files: move the item from this `WORK_QUEUE.md` to `PROJECT_TRACKING.md` Section 4 (Implementation Status)

### When client sends a new BRD version

Use this exact prompt for the AI:

> Read `way4tech_logistics/docs/WORK_QUEUE.md` and `way4tech_logistics/PROJECT_TRACKING.md` fully. Then compare the new BRD attached. List ONLY truly new items (not already in the requirement matrix). For each: section reference, major/minor, dev days estimate. Skip minor modifications and UI polish. Format as a clean change-request table with draft client message.

---

*Last updated: 2026-04-16 after completing 7 quick wins from client's latest feedback. Next action recommended: execute Tier A items A1-A6 (A7 blocked on Q9).*
