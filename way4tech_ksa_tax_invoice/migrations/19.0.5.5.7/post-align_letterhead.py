# -*- coding: utf-8 -*-
"""Give every company on the KSA letterhead layout a paper format that can
print it (see res_company._way4tech_align_letterhead). Companies already set
up correctly are not touched. Idempotent."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    # active_test=False: an archived company is corrected too, so it prints
    # correctly if it is ever reactivated.
    companies = env['res.company'].with_context(active_test=False).search([])
    changed = companies._way4tech_align_letterhead()
    for company in changed:
        _logger.info("Letterhead alignment: company %s (%s) now prints with %s",
                     company.id, company.name, company.paperformat_id.name)
    _logger.info("Letterhead alignment: %s of %s companies corrected",
                 len(changed), len(companies))
