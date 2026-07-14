# -*- coding: utf-8 -*-
"""KSA sale + purchase journal setup: prefixes + monthly-seed helper.

Runs from a ``<function>`` data record on module install/upgrade. Only touches
KSA companies (country=SA or partner VAT starting with '3'). Never renames a
journal whose code is already in use elsewhere in the same company (to keep
Odoo's uniqueness constraint intact).

Monthly-reset itself is driven by ``account.move._get_starting_sequence``
(see account_move_sequence.py) — Odoo auto-detects monthly reset once a move
with ``PREFIX/YYYY/MM/NNNN`` name exists in the journal. To bootstrap the
transition FROM an existing yearly-named sequence, call
``action_apply_ksa_monthly_seed()`` which creates + immediately cancels a
dummy move with the correct monthly name, seeding the pattern for Odoo.
"""
from datetime import date

from odoo import api, models


def _is_ksa_company(comp):
    return (
        (comp.country_id and comp.country_id.code == "SA")
        or ((comp.partner_id.vat or "").startswith("3"))
    )


class AccountJournal(models.Model):
    _inherit = "account.journal"

    @api.model
    def _apply_ksa_monthly_sequences(self):
        """Ensure KSA sale journal → code 'INV', purchase → 'BILL' (when free).

        We DELIBERATELY do NOT set ``sequence_override_regex`` — a strict
        override regex breaks Odoo's ``_compute_split_sequence`` for
        draft-state moves (name = '/'). Monthly reset is instead driven by
        the ``_get_starting_sequence`` override on ``account.move``.
        """
        for j in self.search([]):
            if not _is_ksa_company(j.company_id) or j.type not in ("sale", "purchase"):
                continue
            desired = "INV" if j.type == "sale" else "BILL"
            if j.code != desired:
                clash = self.search([
                    ("company_id", "=", j.company_id.id),
                    ("code", "=", desired),
                    ("id", "!=", j.id),
                ], limit=1)
                if not clash:
                    j.code = desired
            # Clear any leftover override_regex from earlier attempts —
            # a stale strict regex here crashes _compute_split_sequence.
            if j.sequence_override_regex:
                j.sequence_override_regex = False

    def action_apply_ksa_monthly_seed(self, seed_date=None):
        """Bootstrap monthly-reset for this journal.

        Creates a draft move dated on ``seed_date`` (defaults to today) with
        an explicitly-set name of ``{code}/{YYYY}/{MM}/0000``, posts, then
        cancels it. This puts a ``PREFIX/YYYY/MM/NNNN``-shaped name into
        the journal — Odoo's next real move will detect monthly reset and
        continue with ``0001``, ``0002`` … resetting at the start of each
        following month automatically.

        Safe to run on a live tenant: the seed move is immediately cancelled
        so it does not affect ledger balances.
        """
        seed_date = seed_date or date.today()
        for j in self:
            if j.type not in ("sale", "purchase"):
                continue
            move_type = "out_invoice" if j.type == "sale" else "in_invoice"
            partner = self.env["res.partner"].search([], limit=1)
            if not partner:
                continue
            seed = self.env["account.move"].with_company(j.company_id).create({
                "move_type": move_type,
                "journal_id": j.id,
                "partner_id": partner.id,
                "invoice_date": seed_date,
                "date": seed_date,
                "ref": "KSA-MONTHLY-SEED",
                "invoice_line_ids": [(0, 0, {
                    "name": "monthly sequence seed", "quantity": 1, "price_unit": 0,
                })],
            })
            # Force the seed name so Odoo detects monthly-reset going forward.
            seed.name = "%s/%04d/%02d/0000" % (j.code, seed_date.year, seed_date.month)
            seed.action_post()
            seed.button_cancel()
        return True
