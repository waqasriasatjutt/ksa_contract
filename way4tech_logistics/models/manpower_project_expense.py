from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ManpowerProjectExpense(models.Model):
    """
    Project-level expense for a Manpower Contract (project type).

    Accounting flow (proper double-entry):
      Dr  Expense Account (wages / accommodation / utilities / furniture / other)
      Cr  Accounts Payable (vendor)

    The vendor bill is posted to accounts payable so it appears in AP aging,
    can be reconciled when paid, and is properly tracked in the GL.

    All bill lines carry the contract's analytic account so the full
    project P&L (revenue from invoice - costs from bills) is visible in
    Accounting → Reporting → Analytic Report.
    """
    _name = 'way4tech.manpower.project.expense'
    _description = 'Manpower Project Expense'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'
    _rec_name = 'description'

    contract_id = fields.Many2one(
        comodel_name='way4tech.manpower.contract',
        string='Contract',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    expense_type = fields.Selection(
        selection=[
            ('worker_wages', 'Worker Wages'),
            ('accommodation', 'Accommodation'),
            ('utilities', 'Utilities'),
            ('furniture', 'Furniture & Equipment'),
            ('transport', 'Transport'),
            ('other', 'Other'),
        ],
        string='Expense Type',
        required=True,
        default='worker_wages',
        tracking=True,
        help='Type determines the default GL expense account from Payroll & Accounting Setup. '
             'You can override the account on this line.',
    )
    description = fields.Char(
        string='Description',
        required=True,
        tracking=True,
        help='Brief description of the expense, e.g. "Wages for 12 workers — March 2026" '
             'or "Accommodation rent — Al Jubail site — March 2026".',
    )
    vendor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Vendor',
        required=True,
        domain=[('supplier_rank', '>', 0)],
        tracking=True,
        help='The supplier or payee for this expense. Required to create the vendor bill.\n'
             'For worker wages, this could be a representative worker, a payroll agent, '
             'or a generic "Project Workers" vendor you create in Contacts.',
    )
    account_id = fields.Many2one(
        comodel_name='account.account',
        string='Expense Account',
        check_company=True,
        tracking=True,
        help='GL account to debit on the vendor bill line. '
             'Auto-filled from Payroll & Accounting Setup based on expense type. '
             'Override here if needed for this specific expense.',
    )
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        required=True,
        tracking=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='contract_id.currency_id',
        string='Currency',
        readonly=True,
        store=True,
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        related='contract_id.analytic_account_id',
        string='Analytic Account',
        store=True,
        readonly=True,
        help='Inherited from the contract. Applied to the vendor bill line so all '
             'project costs appear in the Analytic Report alongside the contract revenue.',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='contract_id.company_id',
        string='Company',
        store=True,
        readonly=True,
    )
    bill_id = fields.Many2one(
        comodel_name='account.move',
        string='Vendor Bill',
        readonly=True,
        copy=False,
        help='Vendor bill created when you click "Create Vendor Bill". Read-only.',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('billed', 'Bill Created'),
        ],
        string='Status',
        default='draft',
        readonly=True,
        tracking=True,
    )

    # ── Auto-fill account from expense type ──────────────────────────────────

    @api.onchange('expense_type')
    def _onchange_expense_type(self):
        if not self.expense_type:
            return
        settings = self.env['way4tech.payroll.settings'].get_for_company(
            (self.company_id or self.env.company).id
        )
        account = self._get_expense_account(settings)
        if account:
            self.account_id = account

    def _get_expense_account(self, settings):
        """Return the configured GL account for this expense type."""
        mapping = {
            'worker_wages': settings.project_wages_account_id,
            'accommodation': settings.project_accommodation_account_id,
            'utilities': settings.project_utilities_account_id,
            'furniture': settings.project_furniture_account_id,
            'transport': settings.project_transport_account_id,
            'other': settings.project_other_expense_account_id,
        }
        return mapping.get(self.expense_type)

    # ── Create vendor bill ────────────────────────────────────────────────────

    def action_create_bill(self):
        self.ensure_one()
        if self.bill_id:
            raise UserError(_('A vendor bill already exists for this expense.'))
        if not self.vendor_id:
            raise UserError(_('Please set a vendor before creating the bill.'))
        if not self.account_id:
            raise UserError(_(
                'No expense account set. Please configure the account in '
                'Configuration → Payroll & Accounting Setup → Project Expenses, '
                'or set it directly on this expense line.'
            ))

        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)

        bill_line_vals = {
            'name': self.description,
            'quantity': 1.0,
            'price_unit': self.amount,
            'account_id': self.account_id.id,
        }
        # Reuse the contract's analytic distribution (multi-account) with
        # legacy single-analytic + company default as fallbacks. Same helper
        # used for customer-side invoices.
        distribution = self.contract_id._resolve_analytic_distribution(settings)
        if distribution:
            bill_line_vals['analytic_distribution'] = distribution

        journal = settings.project_expense_journal_id or self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.vendor_id.id,
            'invoice_date': self.date,
            'company_id': self.company_id.id,
            'ref': '%s / %s' % (self.contract_id.name, self.description),
            'invoice_line_ids': [(0, 0, bill_line_vals)],
        }
        if journal:
            bill_vals['journal_id'] = journal.id

        # Project + Entry Category from the contract propagate onto the
        # vendor-bill header. Contract's explicit choice wins; fall back to
        # the generic "Others" category if the contract has none.
        if self.contract_id.way4tech_project_id:
            bill_vals['way4tech_project_id'] = self.contract_id.way4tech_project_id.id
        if self.contract_id.way4tech_category_id:
            bill_vals['way4tech_category_id'] = self.contract_id.way4tech_category_id.id
        else:
            _category = self.env.ref('way4tech_logistics.category_others', raise_if_not_found=False)
            if _category:
                bill_vals['way4tech_category_id'] = _category.id
        bill = self.env['account.move'].create(bill_vals)
        self.write({'bill_id': bill.id, 'state': 'billed'})

        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_bill(self):
        self.ensure_one()
        if not self.bill_id:
            raise UserError(_('No vendor bill linked to this expense.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'res_id': self.bill_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
