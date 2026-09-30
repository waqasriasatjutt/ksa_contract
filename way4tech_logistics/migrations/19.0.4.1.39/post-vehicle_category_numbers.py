# -*- coding: utf-8 -*-
"""Renumber the fleet per Vehicle Category (TRUCK-001, CAR-001, BUS-001).

The vehicles carried a single running counter. The client asked for a series
per category, so each category is renumbered from 001 in the order the
vehicles were created, and each category's sequence is left pointing at the
next free number. Idempotent: a vehicle that already holds a number in its
category's format keeps it.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Vehicle = env['fleet.vehicle'].with_context(active_test=False)
    vehicles = Vehicle.search([], order='id')
    per_category = {}
    for vehicle in vehicles:
        per_category.setdefault(vehicle.vehicle_category or 'other', env['fleet.vehicle'])
        per_category[vehicle.vehicle_category or 'other'] |= vehicle
    for category, records in per_category.items():
        sequence = Vehicle._way4tech_category_sequence(category)
        prefix = sequence.prefix or ''
        for vehicle in records:
            current = vehicle.way4tech_sequence or ''
            if current.startswith(prefix) and current != prefix:
                continue  # already numbered in this category's format
            vehicle.with_context(tracking_disable=True).way4tech_sequence = sequence.next_by_id()
        _logger.info("Fleet numbering: %s vehicles in category %s now use %s001 upwards",
                     len(records), category, prefix)
