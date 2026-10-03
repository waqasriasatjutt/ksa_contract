# -*- coding: utf-8 -*-
"""Carry the single analytic account onto the new distribution for Salary
Imports and the company settings, and give any duplicated Equipment Rental
reference a number of its own. Idempotent.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})

    # analytic account -> analytic distribution
    for model, field in (('way4tech.salary.import', 'analytic_account_id'),
                         ('way4tech.payroll.settings', 'default_analytic_account_id')):
        if model not in env or field not in env[model]._fields:
            continue
        records = env[model].with_context(active_test=False).search(
            [(field, '!=', False), ('analytic_distribution', '=', False)])
        for record in records:
            record.analytic_distribution = {str(record[field].id): 100}
        if records:
            _logger.info("Pending wave 2: %s %s records carried over", len(records), model)

    # equipment rental references: one number per record
    for model, code in (('way4tech.equipment.rental', 'way4tech.equipment.rental'),
                        ('way4tech.equipment.rental.inbound', 'way4tech.equipment.rental.inbound')):
        if model not in env:
            continue
        seen, fixed = set(), 0
        for record in env[model].with_context(active_test=False).search([], order='id'):
            name = record.name or ''
            if not name or name in ('New', 'new') or name in seen:
                new_name = env['ir.sequence'].next_by_code(code)
                while new_name in seen:
                    new_name = env['ir.sequence'].next_by_code(code)
                if new_name:
                    record.with_context(tracking_disable=True).name = new_name
                    name, fixed = new_name, fixed + 1
            seen.add(name)
        if fixed:
            _logger.info("Pending wave 2: %s duplicate/empty %s references renumbered", fixed, model)
