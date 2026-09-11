from odoo import fields, models


class Way4techTag(models.Model):
    """Free multi-select Tag master used on invoices and journal entries for
    flexible filtering/reporting. Managed in Configuration -> Tags. Shared
    across companies."""
    _name = 'way4tech.tag'
    _description = 'Tag'
    _order = 'name'

    name = fields.Char(string='Tag', required=True, index=True)
    color = fields.Integer(string='Color')
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        'unique(name)',
        'A tag with this name already exists.',
    )
