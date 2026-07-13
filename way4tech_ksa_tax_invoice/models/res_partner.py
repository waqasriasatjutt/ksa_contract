# -*- coding: utf-8 -*-
from odoo import fields, models


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
