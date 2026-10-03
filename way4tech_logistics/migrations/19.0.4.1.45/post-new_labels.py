# -*- coding: utf-8 -*-
"""Documents raised while their record still read "New".

Before each company had its own number series, a record created under a company
other than the first got no reference at all and stayed called "New". Anything
raised from it copied that word, so posted bills read "Driver Basic Salary - New"
and "Trip Costs: New". The records themselves were given real references in the
upgrade before this one; this carries those references onto the documents they
produced.

Each document is reached through the record that owns it, so a label can only
ever be given the reference of the record it was named after. Labels only: no
amount, account, date or document number is touched, and the chatter history is
left alone because it records what the value used to be.

Idempotent.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# model, the field holding its reference, the fields holding its documents
OWNERS = [
    ('way4tech.truck.trip', 'name', ('invoice_id', 'cost_move_id')),
    ('way4tech.investor.payable', 'name', ('bill_id',)),
    ('fleet.vehicle.log.services', 'way4tech_ref', ('way4tech_bill_id',)),
    ('way4tech.equipment.rental', 'name', ('invoice_id',)),
    ('way4tech.equipment.rental.inbound', 'name', ('bill_id',)),
    ('way4tech.salary.import', 'name', ('accounting_move_id',)),
]

# "... - New" or "...: New", at the end or before a space or a slash. Narrow on
# purpose: a label that merely contains the word New is not touched.
PATTERN = r'([-:] )New($|[ /])'


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})

    fixed = 0
    for model, ref_field, move_fields in OWNERS:
        if model not in env:
            continue
        fields_present = [f for f in move_fields if f in env[model]._fields]
        if not fields_present:
            continue
        domain = (['|'] * (len(fields_present) - 1)
                  + [(field, '!=', False) for field in fields_present])
        records = env[model].sudo().with_context(active_test=False).search(domain)
        for record in records:
            reference = record[ref_field]
            if not reference or reference == 'New':
                continue
            moves = env['account.move']
            for field in fields_present:
                moves |= record[field].exists()
            if not moves:
                continue
            cr.execute(
                """UPDATE account_move_line
                      SET name = regexp_replace(name, %s, %s)
                    WHERE move_id IN %s AND name ~ %s""",
                (PATTERN, r'\1' + reference.replace('\\', r'\\') + r'\2',
                 tuple(moves.ids), PATTERN))
            fixed += cr.rowcount
            cr.execute(
                """UPDATE account_move
                      SET ref = regexp_replace(ref, %s, %s)
                    WHERE id IN %s AND ref ~ %s""",
                (PATTERN, r'\1' + reference.replace('\\', r'\\') + r'\2',
                 tuple(moves.ids), PATTERN))
            fixed += cr.rowcount
    if fixed:
        _logger.info('Document code: %s labels and references that still read '
                     '"New" now carry their record\'s reference', fixed)
