# -*- coding: utf-8 -*-
"""One letterhead on every company, not only the ones already using it.

The corrector written in September only looked at companies that had already
been put on this layout, so a company left on an Odoo stock layout kept a paper
format with a reserved top band and its letterhead started half way down the
page. Every company now adopts the layout and, where its format cannot print
the letterhead, that format too. A company already set up correctly is left
exactly as it is. Idempotent.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    companies = env['res.company'].sudo().with_context(
        active_test=False).search([])
    changed = companies._way4tech_adopt_letterhead_layout()
    _logger.info(
        "Letterhead: %s of %s companies moved onto the KSA letterhead layout "
        "or its paper format", len(changed), len(companies))
