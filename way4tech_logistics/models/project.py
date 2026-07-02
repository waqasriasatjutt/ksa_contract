from odoo import fields, models


class Way4techProject(models.Model):
    """Simple Project master — a dropdown used on invoices, journal entries
    and reports so revenue/costs can be grouped by project. Managed by
    Admin/Manager in Configuration -> Projects. Shared across companies
    (like Entry Category) to avoid per-company duplication."""
    _name = 'way4tech.project'
    _description = 'Project'
    _order = 'name'

    name = fields.Char(string='Project', required=True, index=True)
    code = fields.Char(string='Code')
    note = fields.Char(string='Description')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('name_uniq', 'unique(name)', 'A project with this name already exists.'),
    ]
