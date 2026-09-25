# -*- coding: utf-8 -*-
"""Carry the single Analytic Account of each Fleet record into the new
Analytic Distribution, so nothing that was already configured looks empty
after the change. Records that already carry a distribution are left alone,
and the old field is kept as a fallback. Idempotent.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

# model, name of the old single-account field
TARGETS = [
    ('way4tech.truck.trip', 'analytic_account_id'),
    ('way4tech.trip.project.allocation', 'analytic_account_id'),
    ('fleet.vehicle.log.services', 'way4tech_analytic_account_id'),
    ('way4tech.equipment.rental', 'analytic_account_id'),
    ('way4tech.equipment.rental.inbound', 'analytic_account_id'),
]


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    for model, field in TARGETS:
        if model not in env or field not in env[model]._fields:
            continue
        records = env[model].with_context(active_test=False).search(
            [(field, '!=', False), ('analytic_distribution', '=', False)])
        for record in records:
            account = record[field]
            record.analytic_distribution = {str(account.id): 100}
        if records:
            _logger.info("Fleet analytic: %s %s records carried over", len(records), model)
