# -*- coding: utf-8 -*-
"""Give every company its references.

The module's sequences were created against the first company only, and
ir.sequence.next_by_code only sees sequences of the active company or of none.
Every other company therefore kept the placeholder "New" on vehicles, trips,
maintenance logs, equipment rentals and investor payables. The sequences are
shared here, and the records still holding the placeholder are numbered.
Idempotent: a record that already has a reference is never renumbered.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# model, field holding the reference, sequence code
TARGETS = [
    ('fleet.vehicle', 'way4tech_sequence', 'way4tech.fleet.vehicle'),
    ('way4tech.truck.trip', 'name', 'way4tech.truck.trip'),
    ('fleet.vehicle.log.services', 'way4tech_ref', 'way4tech.truck.maintenance'),
    ('way4tech.equipment.rental', 'name', 'way4tech.equipment.rental'),
    ('way4tech.equipment.rental.inbound', 'name', 'way4tech.equipment.rental.inbound'),
    ('way4tech.investor.payable', 'name', 'way4tech.investor.payable'),
]


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    sequences = env['ir.sequence'].search([('code', 'like', 'way4tech.%'),
                                           ('company_id', '!=', False)])
    if sequences:
        sequences.write({'company_id': False})
        _logger.info("Fleet references: %s sequences shared with every company", len(sequences))
    Sequence = env['ir.sequence']
    for model, field, code in TARGETS:
        if model not in env:
            continue
        records = env[model].with_context(active_test=False).search(
            ['|', (field, '=', False), (field, 'in', ('New', 'new'))])
        done = 0
        for record in records:
            reference = Sequence.with_company(record.company_id or env.company).next_by_code(code)
            if reference:
                record.with_context(tracking_disable=True).write({field: reference})
                done += 1
        if records:
            _logger.info("Fleet references: %s of %s %s records numbered",
                         done, len(records), model)
