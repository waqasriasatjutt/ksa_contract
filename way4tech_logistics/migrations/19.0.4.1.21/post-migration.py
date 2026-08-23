# -*- coding: utf-8 -*-
"""Post-migration for 19.0.4.1.21 — ITEM 2 (2026-08).

Other Payable rows now follow their journal entry's live state both ways
(the shared move-sync gained the 'entry' move type + a 'created_draft' middle
state). Any Other Payable line/block whose journal entry was RESET to draft in
Accounting BEFORE this fix was left stuck at 'posted' — still counted on the
Billing Summary and still badged as posted. Re-sync every linked row from its
entry's current state so those correct themselves on upgrade:

    entry posted   -> 'posted'
    entry draft    -> 'created_draft'   (drops out of the Billing Summary)
    entry cancelled-> 'draft' + release the link

Idempotent — a row already in the right state is skipped.
"""

from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for model_name in ('way4tech.manpower.other.payable',
                        'way4tech.manpower.other.payable.block'):
        Model = env[model_name]
        for rec in Model.search([('move_id', '!=', False)]):
            st = rec.move_id.state
            if st == 'posted':
                target, release = 'posted', False
            elif st == 'cancel':
                target, release = 'draft', True
            else:  # draft
                target, release = 'created_draft', False
            if rec.state != target or (release and rec.move_id):
                vals = {'state': target}
                if release:
                    vals['move_id'] = False
                rec.write(vals)
