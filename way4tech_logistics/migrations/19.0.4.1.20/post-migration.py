# -*- coding: utf-8 -*-
"""Post-migration for 19.0.4.1.20 — Item 3 (2026-08).

Other Payable is now folded into BOTH Gross Profit and Total Project Expense:
    Total Project Expense = Total Project CGS + Operating Expenses + Total Other Payable
    Gross Profit          = Total Invoiced - Total Project CGS - Total Other Payable

pp_gross_profit / bs_total_project_exp_all (and everything derived from them:
net profit, profit after budget/actual, commission KPIs, KPI %s) are STORED
computed fields. A changed compute method does NOT retro-recompute existing
rows, so any contract that already carries an Other-Payable amount would keep
its old (pre-fix) figures until the record is touched again. Recompute them all
here so the numbers refresh the instant the module upgrades, on every
environment. Idempotent — safe to re-run.
"""

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    recs = env['way4tech.manpower.contract'].search([])
    if not recs:
        return
    recs._compute_kpi_summary()
    # Commission KPIs depend on pp_actual_profit / bs_total_project_exp_all,
    # which the line above just changed — refresh them in the same pass.
    if hasattr(recs, '_compute_commission_kpis'):
        recs._compute_commission_kpis()
    recs.flush_recordset()
