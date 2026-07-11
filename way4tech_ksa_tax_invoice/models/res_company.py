# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    x_name_ar = fields.Char(string='Arabic Name')
    x_aramco_logo = fields.Binary(string='Saudi Aramco Vendor Logo')
    x_aramco_vendor_code = fields.Char(string='Saudi Aramco Vendor Code')

    @api.model
    def _apply_ksa_atco_setup(self):
        view = self.env.ref(
            'way4tech_ksa_tax_invoice.external_layout_atco',
            raise_if_not_found=False,
        )
        paperformat = self.env.ref(
            'way4tech_ksa_tax_invoice.paperformat_ksa_tax_invoice',
            raise_if_not_found=False,
        )
        if not view or not paperformat:
            return
        for c in self.search([]):
            country_code = c.partner_id.country_id.code or ''
            vat = c.partner_id.vat or ''
            if country_code != 'SA' and not vat.startswith('3'):
                continue
            vals = {}
            if not c.external_report_layout_id:
                vals['external_report_layout_id'] = view.id
            if not c.paperformat_id:
                vals['paperformat_id'] = paperformat.id
            if vals:
                c.write(vals)
