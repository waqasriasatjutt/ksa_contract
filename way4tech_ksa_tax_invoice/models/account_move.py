# -*- coding: utf-8 -*-
import base64
import io

from odoo import api, fields, models


def _tlv(tag, value):
    """ZATCA TLV field: 1-byte tag + 1-byte length + UTF-8 value."""
    b = (value or '').encode('utf-8')
    return bytes([tag, len(b)]) + b


class AccountMove(models.Model):
    _inherit = 'account.move'

    # ZATCA QR (base64 PNG) built from the invoice data already in Odoo:
    #   seller name, seller VAT, timestamp, grand total (incl VAT), VAT total.
    ksa_qr_image = fields.Char(compute='_compute_ksa_qr_image')
    ksa_amount_words = fields.Char(compute='_compute_ksa_amount_words')
    # Invoice Period auto-derived from the accounting date (o.date), formatted
    # like "JUNE-2026". Rendered in the Invoice Period column of the KSA tax
    # invoice's dates table.
    ksa_invoice_period = fields.Char(compute='_compute_ksa_invoice_period')

    @api.depends('company_id', 'amount_total', 'amount_tax', 'invoice_date', 'date')
    def _compute_ksa_qr_image(self):
        for move in self:
            move.ksa_qr_image = False
            try:
                company = move.company_id
                seller = company.display_name or company.name or ''
                vat = (company.partner_id.vat or '') if company.partner_id else ''
                d = move.invoice_date or move.date
                ts = ('%sT00:00:00Z' % d) if d else ''
                tlv = (
                    _tlv(1, seller)
                    + _tlv(2, vat)
                    + _tlv(3, ts)
                    + _tlv(4, '%.2f' % (move.amount_total or 0.0))
                    + _tlv(5, '%.2f' % (move.amount_tax or 0.0))
                )
                payload = base64.b64encode(tlv).decode()
                import qrcode
                img = qrcode.make(payload)
                buf = io.BytesIO()
                img.save(buf, format='PNG')
                move.ksa_qr_image = base64.b64encode(buf.getvalue()).decode()
            except Exception:
                move.ksa_qr_image = False

    @api.depends('amount_total', 'currency_id')
    def _compute_ksa_amount_words(self):
        for move in self:
            try:
                move.ksa_amount_words = move.currency_id.amount_to_text(move.amount_total or 0.0)
            except Exception:
                move.ksa_amount_words = ''

    @api.depends('date', 'invoice_date')
    def _compute_ksa_invoice_period(self):
        for move in self:
            d = move.date or move.invoice_date
            # Format: "MM, YYYY" — e.g. accounting date 2026-06-30 -> "06, 2026".
            move.ksa_invoice_period = d.strftime('%m, %Y') if d else ''
