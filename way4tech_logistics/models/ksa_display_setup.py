# -*- coding: utf-8 -*-
"""CR3-FINAL round 2 — Bug 8 (date/month format) + Polish 9 (2 decimals).

Both are pure DISPLAY settings. Neither touches a stored value, a posted
document or an existing record — decimal.precision and res.lang.date_format
only affect how numbers and dates are rendered and rounded on NEW input.

Run as an idempotent data hook on every upgrade so the two databases can
never drift apart again, which is what produced the mixed 22/07/2026 vs
2026-07-22 output the client reported.
"""
import logging

from odoo import api, models

_logger = logging.getLogger(__name__)

# Bug 8: dates d/m/y everywhere. Month/period fields are already produced as
# %m/%Y by their own computes (way4tech_inv_month, ksa_invoice_period,
# bill_month, budget month), so only the date side needs enforcing here.
KSA_DATE_FORMAT = '%d/%m/%Y'

# Polish 9: two decimals everywhere. These are the precisions Odoo applies to
# invoice/bill line Quantity and Unit Price, which were rendering as
# 2.000000 and 1,000.000000.
KSA_PRECISIONS = {
    'Product Unit of Measure': 2,
    'Product Price': 2,
    'Discount': 2,
}


class Way4TechKsaDisplaySetup(models.AbstractModel):
    _name = 'way4tech.ksa.display.setup'
    _description = 'KSA display-format setup (dates + decimal precision)'

    @api.model
    def _apply_ksa_display_settings(self):
        changed = []

        # ── Dates ─────────────────────────────────────────────────────────
        langs = self.env['res.lang'].with_context(active_test=False).search([])
        for lang in langs:
            if lang.date_format != KSA_DATE_FORMAT:
                lang.date_format = KSA_DATE_FORMAT
                changed.append('lang %s date_format' % lang.code)

        # ── Decimal precision ─────────────────────────────────────────────
        Precision = self.env['decimal.precision']
        for name, digits in KSA_PRECISIONS.items():
            rec = Precision.search([('name', '=', name)], limit=1)
            if rec and rec.digits != digits:
                # Lowering digits is display/rounding only; stored numeric
                # values are untouched and posted documents keep their amounts.
                rec.digits = digits
                changed.append('precision %s -> %s' % (name, digits))

        # ── Bust cached asset bundles ─────────────────────────────────────
        # A res.lang format change does not reach the browser until the
        # compiled web assets are regenerated — users otherwise keep seeing
        # the old format until a hard refresh. Same lesson as the 2026-07-15
        # date-format change.
        if changed:
            stale = self.env['ir.attachment'].search([
                ('name', 'like', '%.assets_%.min.%'),
            ])
            n_assets = len(stale)
            if stale:
                stale.unlink()
            _logger.info(
                'CR3-FINAL Bug8/Polish9: applied %s; cleared %s asset bundle(s).',
                ', '.join(changed), n_assets,
            )
        else:
            _logger.info(
                'CR3-FINAL Bug8/Polish9: display settings already correct.',
            )
        return True
