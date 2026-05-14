"""Pre-migration for 19.0.2.0.02.

Turn `way4tech.entry.category` into a SHARED model (no per-company `company_id`):

1. Dedupe duplicate (name) records across companies — keep the lowest-id one,
   redirect any `account.move.way4tech_category_id` references to the kept record,
   then delete the duplicates. (Done case-insensitively/whitespace-trimmed so
   "Advance" + " Advance " + "advance" merge into one.)
2. Drop the old per-company unique constraint
   `way4tech_entry_category_name_company_uniq` (`UNIQUE(name, company_id)`) so the
   new `UNIQUE(name)` constraint Odoo applies during this same upgrade succeeds.
3. NULL out `company_id` on remaining records so they're cleanly shared (the
   field is removed from the Python model in this version; the DB column lingers
   harmlessly until a future cleanup).

Runs BEFORE Odoo applies the new schema/constraints, so the upgrade won't fail
on existing per-company duplicates.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        # Fresh install — no existing data to migrate.
        return

    # 1. Dedupe by trimmed lower-cased name; redirect refs; delete losers.
    cr.execute("""
        SELECT TRIM(LOWER(name)) AS key,
               MIN(id)            AS keep_id,
               ARRAY_AGG(id ORDER BY id) AS all_ids
          FROM way4tech_entry_category
         GROUP BY TRIM(LOWER(name))
        HAVING COUNT(*) > 1
    """)
    dup_groups = cr.fetchall()
    merged = 0
    for _key, keep_id, all_ids in dup_groups:
        drop_ids = tuple(i for i in all_ids if i != keep_id)
        if not drop_ids:
            continue
        cr.execute(
            "UPDATE account_move "
            "   SET way4tech_category_id = %s "
            " WHERE way4tech_category_id IN %s",
            (keep_id, drop_ids),
        )
        cr.execute(
            "DELETE FROM way4tech_entry_category WHERE id IN %s",
            (drop_ids,),
        )
        merged += len(drop_ids)
    _logger.info(
        "way4tech_logistics: deduped %s duplicate entry-category records "
        "across %s name groups", merged, len(dup_groups),
    )

    # 2. Drop the old (name, company_id) unique constraint so the new UNIQUE(name)
    #    constraint can be applied cleanly. Odoo doesn't auto-drop removed
    #    constraints, so we do it explicitly.
    cr.execute(
        "ALTER TABLE way4tech_entry_category "
        "DROP CONSTRAINT IF EXISTS way4tech_entry_category_name_company_uniq"
    )

    # 3. Clear lingering company_id values so existing records are visibly shared.
    #    The column itself is left in place (Odoo norm — removed fields don't drop
    #    columns), but its values are zeroed.
    cr.execute(
        "UPDATE way4tech_entry_category "
        "   SET company_id = NULL "
        " WHERE company_id IS NOT NULL"
    )
