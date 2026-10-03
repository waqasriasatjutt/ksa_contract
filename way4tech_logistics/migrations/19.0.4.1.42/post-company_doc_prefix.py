# -*- coding: utf-8 -*-
"""Take "WAY4TECH" out of the client's document references.

Each company now mints its own numbers with its own short code. Existing
references keep their shape and their number, so a record the client already
knows as WAY4TECH/TRIP/2026/0003 becomes AZT/TRIP/2026/0003 and nothing has to
be looked up twice. Each new per-company series then starts above the highest
number already used by that company, so the next record cannot collide.

Idempotent: a reference that no longer starts with WAY4TECH is left alone.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# model, reference field, the token in its old shared series, base sequence
# code, label - matching the calls in the models.
SERIES = [
    ('way4tech.truck.trip', 'name', 'TRIP',
     'way4tech.truck.trip', 'Truck Trip'),
    ('fleet.vehicle.log.services', 'way4tech_ref', 'MAINT',
     'way4tech.truck.maintenance', 'Maintenance Log'),
    ('way4tech.equipment.rental', 'name', 'RENT',
     'way4tech.equipment.rental', 'Equipment Rental'),
    ('way4tech.equipment.rental.inbound', 'name', 'RENT-IN',
     'way4tech.equipment.rental.inbound', 'Inbound Equipment Rental'),
    ('way4tech.investor.payable', 'name', 'INV',
     'way4tech.investor.payable', 'Fleet Profitability'),
    ('way4tech.salary.import', 'name', 'SAL/IMP',
     'way4tech.salary.import', 'Salary Import'),
    ('way4tech.employee.cost', 'name', 'EMP/COST',
     'way4tech.employee.cost', 'Employee Cost'),
    ('way4tech.employee.deduction', 'name', 'DED',
     'way4tech.employee.deduction', 'Employee Deduction'),
    ('way4tech.asset.register', 'ref', 'ASSET',
     'way4tech.asset.register', 'Asset Register'),
]


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Every company that existed before this upgrade gets a code suggested from
    # its name. Companies created after it get one as they are created.
    for company in env['res.company'].sudo().with_context(active_test=False).search([]):
        if not company.way4tech_doc_prefix:
            company.way4tech_doc_prefix = company._way4tech_suggest_doc_prefix()

    renamed = 0
    for model, field, token, base_code, label in SERIES:
        if model not in env or field not in env[model]._fields:
            continue
        old_prefix = 'WAY4TECH/%s/' % token
        records = env[model].sudo().with_context(active_test=False).search(
            [(field, '=like', old_prefix + '%')])
        # highest number already used, per company, so the new series starts
        # behind it rather than on top of it
        highest = {}
        for record in records:
            company = record.company_id if 'company_id' in record._fields else env.company
            company = company or env.company
            reference = record[field]
            record[field] = '%s/%s' % (
                company.way4tech_doc_prefix, reference[len('WAY4TECH/'):])
            renamed += 1
            tail = reference.rsplit('/', 1)[-1]
            if tail.isdigit():
                highest[company.id] = max(highest.get(company.id, 0), int(tail))
        for company_id, number in highest.items():
            company = env['res.company'].browse(company_id)
            sequence = company._way4tech_doc_sequence(base_code, label, token)
            if sequence.number_next_actual <= number:
                sequence.number_next_actual = number + 1
    if renamed:
        _logger.info("Document code: %s references moved off the WAY4TECH "
                     "prefix onto their own company's code", renamed)

    # Records created while the old series were pinned to one company got no
    # reference at all and still read "New" on screen and in the reports. Mint
    # a real one for each from its own company's series.
    minted = 0
    for model, field, token, base_code, label in SERIES:
        if model not in env or field not in env[model]._fields:
            continue
        # Only the placeholders a failed mint leaves behind, never a value
        # somebody typed.
        records = env[model].sudo().with_context(active_test=False).search(
            ['|', (field, '=', False), (field, 'in', ('', '/', 'New'))])
        for record in records:
            company = record.company_id if 'company_id' in record._fields else env.company
            company = company or env.company
            record[field] = company._way4tech_doc_sequence(
                base_code, label, token).next_by_id()
            minted += 1
    if minted:
        _logger.info("Document code: %s records that still read \"New\" were "
                     "given a reference", minted)
