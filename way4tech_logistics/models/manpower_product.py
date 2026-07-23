# -*- coding: utf-8 -*-
"""CR4 item 5 — a module-local product master list.

Deliberately NOT Odoo's product.product and NOT linked to it: selecting one
must never pull an account or a tax onto the line (item 5e). Just a name the
user can attach to Project Income and Project Direct Cost lines, retired via
Active rather than deleted so historical records keep their reference.
"""
from odoo import fields, models


class Way4TechManpowerProduct(models.Model):
    _name = 'way4tech.manpower.product'
    _description = 'Manpower Product (module-local list)'
    _order = 'name'

    name = fields.Char(string='Name', required=True, translate=True)
    active = fields.Boolean(string='Active', default=True)
    # Scoped to a settings record so it edits as an "Add a line" table on the
    # Manpower tab, exactly like the category map and Commission Rules. On a
    # single-company system that is one shared list.
    settings_id = fields.Many2one(
        'way4tech.payroll.settings', string='Settings', ondelete='cascade',
    )
    company_id = fields.Many2one(
        related='settings_id.company_id', store=True, readonly=True,
    )
