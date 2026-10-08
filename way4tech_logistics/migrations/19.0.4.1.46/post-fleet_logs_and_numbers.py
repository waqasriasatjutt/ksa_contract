# -*- coding: utf-8 -*-
"""Two corrections to data already in the books.

Maintenance logs Odoo made by itself. Posting the truck purchase bill left
eight maintenance logs behind, one per vehicle on the bill, each carrying the
price of the vehicle as its "maintenance cost" and each locked against deletion
by the standard fleet code. They are released from that bill and marked as not
maintenance, so the Profitability Report leaves them out and the client can
delete them. The purchase bill, its payment and its assets are not touched.

Invoice numbers handed to two documents. An invoice that was posted, reset to
draft and left sitting keeps its number, and another invoice posted in the
meantime takes the same one. The draft of each such pair gives its number up and
will take the next free one when it is posted. Posted documents keep theirs.

Idempotent.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})

    # ── maintenance logs that came from a bill of their own accord ────────
    logs = env['fleet.vehicle.log.services'].sudo().with_context(
        active_test=False).search([('account_move_line_id', '!=', False)])
    # A log our own Create Vendor Bill produced carries way4tech_bill_id, and
    # that is the only bill a maintenance log may belong to.
    strays = logs.filtered(lambda log: not log.way4tech_bill_id)
    if strays:
        strays.write({
            'way4tech_not_maintenance': True,
            'account_move_line_id': False,
        })
        _logger.info(
            "Maintenance: %s logs released from the bill Odoo attached them to "
            "and marked as not maintenance", len(strays))

    # ── a number is never on two documents ────────────────────────────────
    cr.execute("""
        SELECT name, journal_id, company_id
          FROM account_move
         WHERE name IS NOT NULL AND name <> '/'
      GROUP BY name, journal_id, company_id
        HAVING count(*) > 1
    """)
    freed = 0
    for name, journal_id, company_id in cr.fetchall():
        twins = env['account.move'].sudo().search([
            ('name', '=', name),
            ('journal_id', '=', journal_id),
            ('company_id', '=', company_id),
        ])
        drafts = twins.filtered(lambda move: move.state == 'draft')
        # Only ever give up a draft's number, and only while a sibling keeps it.
        if drafts and len(drafts) < len(twins):
            drafts.write({'name': False})
            freed += len(drafts)
        elif len(drafts) == len(twins) and len(drafts) > 1:
            # every one of them is a draft: the oldest keeps the number
            drafts[1:].write({'name': False})
            freed += len(drafts) - 1
    if freed:
        _logger.info("Numbering: %s draft documents gave up a number another "
                     "document already carries", freed)
