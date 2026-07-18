# -*- coding: utf-8 -*-
"""CR2 G5 (19.0.2.9.0) — post-migration.

Backfills state='confirmed' on every pre-existing budget line. The new
state field defaults to 'draft' and only 'confirmed' lines contribute
to bs_total_budget_cost / bs_total_actual_cost — without this backfill,
the upgrade would silently zero out the Billing Summary Budget columns
for every existing tenant.
"""


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        "UPDATE way4tech_manpower_contract_budget_line "
        "SET state = 'confirmed' "
        "WHERE state IS NULL OR state = 'draft'"
    )
