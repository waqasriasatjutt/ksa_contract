# -*- coding: utf-8 -*-
import json
import logging
import urllib.parse
import urllib.request

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Free Google Translate endpoint (unofficial but stable). No API key needed.
# Returns nested JSON — first cell of the first array holds the translation.
_GT_URL = 'https://translate.googleapis.com/translate_a/single'


def _google_translate_en_to_ar(text):
    """Translate English text to Arabic via Google's public endpoint.

    Returns the translated string, or an empty string on any failure — we
    NEVER raise: a partner save must not fail because Google is offline.
    """
    if not text or not text.strip():
        return ''
    try:
        params = {
            'client': 'gtx',
            'sl': 'en',
            'tl': 'ar',
            'dt': 't',
            'q': text.strip(),
        }
        url = _GT_URL + '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        # data = [[[<translated>, <original>, ...], ...], ...]
        chunks = data[0] if data and isinstance(data, list) else []
        return ''.join(chunk[0] for chunk in chunks if chunk and chunk[0]) or ''
    except Exception as e:
        _logger.debug('Google Translate failed for %r: %s', text, e)
        return ''


# Map of English source field -> Arabic target field on res.partner.
_TRANSLATE_MAP = {
    'name': 'x_name_ar',
    'street': 'x_street_ar',
    'city': 'x_city_ar',
    'x_district': 'x_district_ar',
}


class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_name_ar = fields.Char(string='Arabic Name')
    x_street_ar = fields.Char(string='Arabic Street')
    x_city_ar = fields.Char(string='Arabic City')
    x_district_ar = fields.Char(string='Arabic District')
    x_country_ar = fields.Char(string='Arabic Country')
    x_building_no = fields.Char(string='Building No')
    x_additional_no = fields.Char(string='Additional No')
    x_district = fields.Char(string='District (English)')

    # ---- Auto-translate hooks ----
    # When an English field is set on create/write, auto-fill the paired Arabic
    # field via Google Translate IF the Arabic field is currently empty. Manual
    # entries in the Arabic tab are always respected — we never overwrite a
    # non-empty Arabic value.

    def _autofill_arabic(self, vals):
        """Return a dict of Arabic fields to add to `vals` for THIS record.

        Called with the already-computed `vals` (English side changes) and the
        current record's state. Only fills targets that will be empty AFTER
        vals are applied.
        """
        out = {}
        for en_field, ar_field in _TRANSLATE_MAP.items():
            # Skip if the Arabic field is being explicitly written this save.
            if ar_field in vals:
                continue
            # Determine effective English + Arabic values after vals applied.
            en_val = vals.get(en_field, self[en_field] if en_field in self._fields else '')
            ar_current = self[ar_field] if ar_field in self._fields else ''
            if not en_val or ar_current:
                continue
            translated = _google_translate_en_to_ar(en_val)
            if translated:
                out[ar_field] = translated
        # Country → Arabic country (name lookup)
        if 'x_country_ar' not in vals and not self.x_country_ar:
            country_id = vals.get('country_id') or self.country_id.id
            if country_id:
                cname = self.env['res.country'].browse(country_id).name or ''
                if cname:
                    translated = _google_translate_en_to_ar(cname)
                    if translated:
                        out['x_country_ar'] = translated
        return out

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            extra = rec._autofill_arabic({})
            if extra:
                super(ResPartner, rec).write(extra)
        return records

    def write(self, vals):
        res = super().write(vals)
        # Only run if at least one source field is in vals (avoid extra Google
        # calls on unrelated updates).
        sources = set(_TRANSLATE_MAP) | {'country_id'}
        if not (set(vals) & sources):
            return res
        for rec in self:
            extra = rec._autofill_arabic(vals)
            if extra:
                super(ResPartner, rec).write(extra)
        return res

    def action_force_arabic_translate(self):
        """Force-fill empty Arabic fields via Google Translate.
        Used by the module's post-upgrade hook and for manual retries.
        """
        for rec in self:
            extra = rec._autofill_arabic({})
            if extra:
                super(ResPartner, rec).write(extra)
        return True

    @api.model
    def _apply_ksa_partner_translation(self):
        """On module upgrade: for every KSA-flagged partner (country=SA or VAT
        starts with '3'), fill any empty Arabic fields via Google Translate.
        Runs once on install/upgrade — no-op if already populated.
        """
        partners = self.search([]).filtered(
            lambda p: (p.country_id and p.country_id.code == 'SA')
                      or (p.vat and p.vat.startswith('3'))
        )
        partners.action_force_arabic_translate()
