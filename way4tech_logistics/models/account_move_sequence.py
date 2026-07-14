# -*- coding: utf-8 -*-
"""Monthly-reset sequence for KSA customer invoices and vendor bills.

Odoo's default sale/purchase journals use a YEARLY-reset name pattern like
``INV/2026/00051``. For KSA operations we want MONTHLY reset with the pattern
``INV/2026/07/0001`` (customer invoices) and ``BILL/2026/07/0001`` (vendor
bills) — counter restarts at 0001 at the start of each calendar month.

Odoo's ``account.move`` name generator picks the format from the LAST posted
move on the same journal via ``_get_last_sequence``. If we set a
``sequence_override_regex`` on the journal that only matches monthly patterns,
existing YEARLY moves won't match — Odoo will then fall back to
``_get_starting_sequence`` (which we override here) to seed the new pattern.

That gives us the transition without renaming any posted moves.
"""
from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_starting_sequence(self):
        """Seed a monthly-reset name for KSA sale/purchase journals."""
        self.ensure_one()
        j = self.journal_id
        is_ksa = (
            (j.company_id.country_id and j.company_id.country_id.code == "SA")
            or ((j.company_id.partner_id.vat or "").startswith("3"))
        )
        if is_ksa and j.type in ("sale", "purchase") and self.date:
            prefix = j.code or ("INV" if j.type == "sale" else "BILL")
            starting = "%s/%04d/%02d/0000" % (prefix, self.date.year, self.date.month)
            if j.payment_sequence:
                starting = "P" + starting
            return starting
        return super()._get_starting_sequence()
