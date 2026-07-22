# -*- coding: utf-8 -*-
"""CR3-FINAL P1 follow-up — re-key contract_month onto start_date.

v19.0.3.0.0 changed ``way4tech.manpower.contract.contract_month`` from
``@api.depends('accounting_date')`` to ``@api.depends('start_date')``.

Changing the depends of an EXISTING stored computed field does not make Odoo
recompute the rows already in the table — it only recomputes when the column
is newly created or something in the (new) dependency chain is written. So
after the upgrade, every pre-existing contract kept the month derived from its
old accounting_date. Caught on devnew: contract 11 had start_date 2026-05-05
but contract_month 2026-07-01.

That value is the uniqueness key behind
``way4tech_manpower_contract_month_unique_idx`` (client + month + project),
so a stale month reserves the wrong monthly slot and mis-groups the record.

This backfills it in one statement. Rows with no start_date keep NULL, which
is exactly what the partial index's ``WHERE contract_month IS NOT NULL`` skips.

Collision safety: the unique index only covers state IN ('active','completed').
Verified before shipping that neither devnew nor devtest has any
(client, start-month, project) collision among those states, so this update
cannot violate it. If a future database does collide, this will raise loudly
during the upgrade rather than silently leave the wrong month behind — which
is the correct failure mode for a uniqueness key.
"""


def migrate(cr, version):
    if not version:
        return
    cr.execute(
        """
        UPDATE way4tech_manpower_contract
           SET contract_month = date_trunc('month', start_date)::date
         WHERE start_date IS NOT NULL
           AND contract_month IS DISTINCT FROM date_trunc('month', start_date)::date
        """
    )
    fixed = cr.rowcount
    cr.execute(
        """
        SELECT COUNT(*) FROM way4tech_manpower_contract
         WHERE start_date IS NOT NULL
           AND contract_month IS DISTINCT FROM date_trunc('month', start_date)::date
        """
    )
    remaining = cr.fetchone()[0]
    import logging
    logging.getLogger(__name__).info(
        "CR3-FINAL P1: re-keyed contract_month onto start_date for %s "
        "contract(s); %s row(s) still mismatched (expected 0).",
        fixed, remaining,
    )
