# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    x_name_ar = fields.Char(string='Arabic Name')
    x_aramco_logo = fields.Binary(string='Saudi Aramco Vendor Logo')
    x_aramco_vendor_code = fields.Char(string='Saudi Aramco Vendor Code')
