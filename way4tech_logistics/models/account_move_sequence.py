# -*- coding: utf-8 -*-
"""Monthly-reset sequence for KSA customer invoices and vendor bills.

Odoo's default sale/purchase journals use YEARLY-reset pattern like
``INV/2026/00051``. KSA business wants MONTHLY reset: ``INV/2026/07/0001``
for customer invoices, ``BILL/2026/07/0001`` for vendor bills — counter
restarts at 0001 at the start of each calendar month.

Two overrides work together to switch existing yearly-numbered journals to
monthly without renaming any posted move:

* ``_get_last_sequence_domain``: when computing the "next" name for a KSA
  sale/purchase move, tell Odoo to IGNORE moves whose name doesn't match
  the monthly ``PREFIX/YYYY/MM/NNNN`` regex. Old ``INV/2026/00051`` moves
  are hidden — Odoo then thinks there is no prior sequence and calls
  ``_get_starting_sequence``.

* ``_get_starting_sequence``: return ``PREFIX/YYYY/MM/0000`` for KSA
  sale/purchase moves. First real move becomes ``PREFIX/YYYY/MM/0001``;
  Odoo's built-in ``_deduce_sequence_number_reset`` then detects monthly
  reset from that name and auto-continues (increments within the month,
  restarts at 0001 on the first of the next month).
"""
from odoo import models


def _is_ksa_sale_purchase(move):
    j = move.journal_id
    if j.type not in ("sale", "purchase"):
        return False
    comp = j.company_id
    return (
        (comp.country_id and comp.country_id.code == "SA")
        or ((comp.partner_id.vat or "").startswith("3"))
    )


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_starting_sequence(self):
        """Seed a monthly-reset name for KSA sale/purchase journals."""
        self.ensure_one()
        if _is_ksa_sale_purchase(self) and self.date:
            j = self.journal_id
            prefix = j.code or ("INV" if j.type == "sale" else "BILL")
            starting = "%s/%04d/%02d/0000" % (prefix, self.date.year, self.date.month)
            if j.payment_sequence:
                starting = "P" + starting
            return starting
        return super()._get_starting_sequence()

    def _get_last_sequence_domain(self, relaxed=False):
        """For KSA sale/purchase moves, only consider prior moves whose name
        matches the monthly ``PREFIX/YYYY/MM/NNNN`` pattern. Legacy yearly-
        named moves (``INV/2026/00051``) are ignored so Odoo starts fresh
        with monthly numbering."""
        where_string, param = super()._get_last_sequence_domain(relaxed)
        if self and _is_ksa_sale_purchase(self):
            where_string += " AND name ~ %(ksa_monthly_regex)s "
            param['ksa_monthly_regex'] = r'^[A-Za-z]+/\d{4}/(0[1-9]|1[0-2])/\d+$'
        return where_string, param
