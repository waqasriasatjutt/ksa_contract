# -*- coding: utf-8 -*-
"""Post-migration for 19.0.2.6.0 — CR2 Group 2.

data/expense_category_data.xml has noupdate="1", so Odoo does NOT re-apply
its <field> values to already-existing category records on upgrade. This
script:
  (1) Backfills the new expense_type bucket column on the 13 pre-existing
      seeded categories per the client's canonical mapping.
  (2) Back-labels legacy project.expense rows (category_id still NULL,
      legacy expense_type set) to the correct new category so they appear
      in the correct tab AND satisfy the newly-required category_id.
  (3) Renames 'Commission Exp' → 'Client Commission' via the ORM (JSONB
      translate field — raw SQL param-binding of a dict crashes psycopg2;
      ORM handles the jsonb conversion cleanly). Runs LAST so a partial
      failure can't roll back steps (1) and (2).
Idempotent: safe to re-run.
"""

from odoo import api, SUPERUSER_ID

# Client's canonical bucket assignment for the 13 pre-existing seeds.
CATEGORY_BUCKET = {
    # DIRECT COST
    'commission_exp':        'direct',
    'equipment_rent_exp':    'direct',
    # OPERATING EXP
    'iqama_renewal':         'operating',
    'telephone_internet':    'operating',
    'fuel':                  'operating',
    'refreshment':           'operating',
    'vehicle_maintenance':   'operating',
    'building_maintenance':  'operating',
    'building_fixtures':     'operating',
    'equipment_maintenance': 'operating',
    'uniform_safety':        'operating',
    'mob_demob':             'operating',
    'chamber':               'operating',
    'utility':               'operating',
    'miscellaneous':         'operating',
}

# Legacy 6-value expense_type -> new category code, so pre-G2 project.expense
# rows (which have category_id NULL) get placed in a sensible tab.
LEGACY_EXPENSE_TYPE_TO_CATEGORY = {
    'worker_wages':  'worker_wages',        # direct (new)
    'accommodation': 'building_rent_exp',   # direct (new)
    'utilities':     'utility',             # operating (existing)
    'furniture':     'building_fixtures',   # operating (existing)
    'transport':     'transportation',      # direct (new)
    'other':         'miscellaneous',       # operating (existing)
}


def migrate(cr, version):
    if not version:
        return

    # (1) Backfill category.expense_type on pre-existing seeds. New seeds
    # already have their bucket set via the XML load that ran before this.
    for code, bucket in CATEGORY_BUCKET.items():
        cr.execute(
            "UPDATE way4tech_expense_category SET expense_type = %s "
            "WHERE code = %s AND (expense_type IS NULL OR expense_type = 'operating')",
            (bucket, code),
        )

    # (2) Legacy project.expense rows with NULL category_id: map from the
    # 6-value expense_type field to a canonical category. This keeps their
    # amounts flowing into the right tab AND satisfies the newly-required
    # category_id column so future writes on those rows don't crash.
    cr.execute(
        "SELECT code, id FROM way4tech_expense_category "
        "WHERE code = ANY(%s)",
        (list(set(LEGACY_EXPENSE_TYPE_TO_CATEGORY.values())),),
    )
    code_to_id = dict(cr.fetchall())
    for legacy_val, new_code in LEGACY_EXPENSE_TYPE_TO_CATEGORY.items():
        new_cat_id = code_to_id.get(new_code)
        if not new_cat_id:
            continue
        cr.execute(
            "UPDATE way4tech_manpower_project_expense "
            "SET category_id = %s "
            "WHERE category_id IS NULL AND expense_type = %s",
            (new_cat_id, legacy_val),
        )

    # (3) Rename Commission Exp → Client Commission via ORM. Runs LAST so
    # a failure here can't roll back (1) and (2). Uses ref() so it only
    # triggers on databases where the seed record actually exists.
    env = api.Environment(cr, SUPERUSER_ID, {})
    commission_cat = env.ref(
        'way4tech_logistics.expense_cat_commission_exp',
        raise_if_not_found=False,
    )
    if commission_cat and commission_cat.name == 'Commission Exp':
        commission_cat.name = 'Client Commission'
