from odoo import api, fields, models, _


class Way4TechEntryCategory(models.Model):
    """
    Dynamic category list for all accounting entries.
    Admin can add / edit / delete categories.
    Categories are enforced as mandatory on account.move posting
    (see account_move_extension.py).
    """
    _name = 'way4tech.entry.category'
    _description = 'Way4Tech Accounting Entry / Invoice Category'
    _order = 'sequence, name'

    name = fields.Char(string='Category', required=True, translate=True)
    code = fields.Char(string='Short Code', size=10)
    sequence = fields.Integer(string='Sequence', default=10)
    apply_to = fields.Selection([
        ('all', 'All Entries'),
        ('invoice', 'Invoices / Bills'),
        ('payment', 'Payments'),
        ('journal', 'Journal Entries'),
    ], string='Applies To', required=True, default='all',
        help='Controls which entry types this category appears on.\n'
             'All Entries: shows everywhere.\n'
             'Invoices/Bills: only on out_invoice, in_invoice, etc.\n'
             'Payments: only on payment entries.\n'
             'Journal Entries: only on manual journal entries.')
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company,
    )
    color = fields.Integer(string='Color Index', default=0)
    notes = fields.Text(string='Notes / Description')

    _sql_constraints = [
        ('name_company_uniq', 'UNIQUE(name, company_id)',
         'Category name must be unique per company.'),
    ]

    @api.model
    def _get_default_categories(self):
        """Return default category names for initial setup."""
        return [
            ('Advance', 'all'),
            ('Loan', 'all'),
            ('Salary Payable', 'all'),
            ('Salary', 'all'),
            ('Rent', 'all'),
            ('Utility Bills', 'all'),
            ('Maintenance', 'all'),
            ('Fuel / Diesel', 'all'),
            ('GOSI / Iqama', 'all'),
            ('Commission', 'invoice'),
            ('Truck Revenue', 'invoice'),
            ('Manpower Revenue', 'invoice'),
            ('Others', 'all'),
        ]
