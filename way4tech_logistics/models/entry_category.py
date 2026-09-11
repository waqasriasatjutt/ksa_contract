from odoo import api, fields, models, _


class Way4TechEntryCategory(models.Model):
    """
    Dynamic category list for all accounting entries.
    Admin can add / edit / delete categories.
    Categories are enforced as mandatory on account.move posting
    (see account_move_extension.py).

    SHARED across all companies — there is intentionally no `company_id` field, so
    one category list is reused everywhere. To migrate existing per-company records
    after this change, see migrations/19.0.2.0.02/pre-migrate.py.
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
    color = fields.Integer(string='Color Index', default=0)
    notes = fields.Text(string='Notes / Description')

    _name_uniq = models.Constraint(
        'UNIQUE(name)',
        'Category name must be unique (categories are shared across all companies).',
    )

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
