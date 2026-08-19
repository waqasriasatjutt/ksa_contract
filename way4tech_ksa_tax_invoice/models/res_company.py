# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    x_name_ar = fields.Char(string='Arabic Name')
    x_aramco_logo = fields.Binary(string='Saudi Aramco Vendor Logo')
    x_aramco_vendor_code = fields.Char(string='Saudi Aramco Vendor Code')

    # Item 2b (2026-08): ONE IBAN shared by every company on the Tax Invoice.
    # Backed by a single global ir.config_parameter (NOT a per-company column),
    # so it is identical on every company and editable from any company's form —
    # changing it anywhere updates it everywhere. Account Number, Bank, Branch
    # and Swift stay per-company (read from the company's own bank record).
    x_shared_iban = fields.Char(
        string='Shared IBAN (all companies)',
        compute='_compute_x_shared_iban', inverse='_inverse_x_shared_iban',
        help='Single IBAN printed on every company\'s Tax Invoice. Stored once '
             'globally, so it is the same on all companies; Account Number, '
             'Bank, Branch and Swift remain per-company.')

    def _compute_x_shared_iban(self):
        val = self.env['ir.config_parameter'].sudo().get_param(
            'way4tech_ksa_tax_invoice.shared_iban', '')
        for c in self:
            c.x_shared_iban = val

    def _inverse_x_shared_iban(self):
        for c in self:
            self.env['ir.config_parameter'].sudo().set_param(
                'way4tech_ksa_tax_invoice.shared_iban', c.x_shared_iban or '')

    def write(self, vals):
        """Mirror x_name_ar to the company's partner record so the tax invoice
        template (which reads bp.x_name_ar / cp.x_name_ar) stays in sync
        without the operator having to fill both places."""
        res = super().write(vals)
        if 'x_name_ar' in vals:
            for c in self:
                if c.partner_id and c.partner_id.x_name_ar != vals['x_name_ar']:
                    c.partner_id.sudo().write({'x_name_ar': vals['x_name_ar']})
        return res

    @api.model
    def _sync_ksa_arabic_to_partner(self):
        """Backfill: copy company.x_name_ar to company.partner_id.x_name_ar
        for every KSA company whose partner is missing the Arabic name. Run
        once on install/upgrade."""
        for c in self.search([]):
            if not c.partner_id or not c.x_name_ar:
                continue
            if not c.partner_id.x_name_ar:
                c.partner_id.sudo().write({'x_name_ar': c.x_name_ar})

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

    @api.model
    def _apply_ksa_date_format(self):
        """Force English (en_US) date_format to DD/MM/YYYY across the system.

        This changes how every date renders in the Odoo backend UI (forms, list
        views, filters) AND in reports — invoice form, sale order, purchase
        order, journal entries, all of it. KSA business norm is DD/MM/YYYY.
        """
        lang = self.env['res.lang'].search([('code', '=', 'en_US')], limit=1)
        if lang and lang.date_format != '%d/%m/%Y':
            lang.sudo().write({'date_format': '%d/%m/%Y'})
