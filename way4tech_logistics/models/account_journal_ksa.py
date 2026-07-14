# -*- coding: utf-8 -*-
"""One-time setup for KSA sale + purchase journals: sequence prefixes and
monthly-reset regex.

Runs from a ``<function>`` data record on module install/upgrade. Only touches
KSA companies (country=SA or partner VAT starting with '3'). Never renames a
journal whose code is already in use elsewhere in the same company (to keep
Odoo's uniqueness constraint intact).
"""
from odoo import api, models

# Matches PREFIX/YYYY/MM/NNNN with an explicit month capture. Used by Odoo's
# ``account.move._deduce_sequence_number_reset`` to detect monthly reset.
# NOTE: every inner group is non-capturing ``(?:...)`` because Odoo's
# ``_compute_split_sequence`` transforms this regex with a naive
# ``?P<name>`` -> ``?:`` sub — any residual capturing group other than
# ``seq`` shifts ``matching.group(1)`` and crashes with AttributeError.
_MONTHLY_REGEX = (
    r"^(?P<prefix1>.*?)"
    r"(?P<year>(?:(?<=\D)|(?<=^))\d{4})"
    r"(?P<prefix2>\D+?)"
    r"(?P<month>0[1-9]|1[0-2])"
    r"(?P<prefix3>\D+?)"
    r"(?P<seq>\d+)"
    r"(?P<suffix>\D*?)$"
)


class AccountJournal(models.Model):
    _inherit = "account.journal"

    @api.model
    def _apply_ksa_monthly_sequences(self):
        """Configure KSA sale + purchase journals for monthly-reset sequences.

        Sale journal: try to hold code ``INV``. Purchase journal: try to hold
        code ``BILL``. If another journal in the same company already owns
        that code, we leave the current code alone (uniqueness). Every KSA
        sale/purchase journal gets ``sequence_override_regex`` set to the
        monthly regex — Odoo then detects monthly reset on the FIRST posted
        move that matches the pattern.
        """
        for j in self.search([]):
            comp = j.company_id
            is_ksa = (
                (comp.country_id and comp.country_id.code == "SA")
                or ((comp.partner_id.vat or "").startswith("3"))
            )
            if not is_ksa or j.type not in ("sale", "purchase"):
                continue
            desired = "INV" if j.type == "sale" else "BILL"
            # Rename only if the target code is free in this company and this
            # journal doesn't already have the desired code.
            if j.code != desired:
                clash = self.search([
                    ("company_id", "=", comp.id),
                    ("code", "=", desired),
                    ("id", "!=", j.id),
                ], limit=1)
                if not clash:
                    j.code = desired
            if j.sequence_override_regex != _MONTHLY_REGEX:
                j.sequence_override_regex = _MONTHLY_REGEX
