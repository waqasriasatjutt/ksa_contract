# -*- coding: utf-8 -*-
"""Take "WAY4TECH" off the documents too, not only off the records.

Renaming the trips, maintenance logs and rentals left the text that had already
been copied onto their invoices and bills: the label on an invoice line, the
line's own reference, and the Reference field of the document. The client still
reads "WAY4TECH/TRIP/2026/0021" on a posted bill although the trip itself has
been called WLS/TRIP/2026/0021 since the last upgrade.

Each company's documents take that company's own code, so the label keeps
pointing at the record it names. Labels only: no amount, account, date or
document number is touched, and the chatter history is left alone because it
records what the value used to be.

The old shared number series are removed at the same time. Nothing draws from
them any more, but they were still listed under Settings with our name on them.

Idempotent.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# table, column - every place a reference was copied as text.
LABEL_COLUMNS = [
    ('account_move_line', 'name'),
    ('account_move_line', 'ref'),
    ('account_move', 'ref'),
]


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})

    renamed = 0
    for company in env['res.company'].sudo().with_context(
            active_test=False).search([]):
        code = company.way4tech_doc_prefix
        if not code:
            continue
        for table, column in LABEL_COLUMNS:
            cr.execute(
                """UPDATE {table} SET {column} = replace({column}, %s, %s)
                   WHERE company_id = %s AND {column} LIKE %s""".format(
                    table=table, column=column),
                ('WAY4TECH/', '%s/' % code, company.id, '%WAY4TECH/%'))
            renamed += cr.rowcount
    if renamed:
        _logger.info("Document code: %s labels and references on invoices and "
                     "bills now carry their company's own code", renamed)

    # The series the records used before each company had its own. Matched on
    # the prefix and on a code that is not one of the per-company ones, so a
    # company that chooses to call itself WAY4TECH keeps its series.
    stale = env['ir.sequence'].sudo().search([
        ('prefix', '=like', 'WAY4TECH/%'),
        ('code', 'not like', '%.company.%'),
    ])
    if stale:
        count = len(stale)
        stale.unlink()
        _logger.info("Document code: removed %s unused WAY4TECH number series",
                     count)
