from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CommissionReceipt(models.Model):
    _name = 'way4tech.commission.receipt'
    _description = 'Commission Receipt'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, name desc'

    name = fields.Char(
        string='Reference',
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Customer',
        required=True,
        tracking=True,
    )
    subcontractor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Subcontractor',
        required=True,
        domain=[('supplier_rank', '>', 0)],
        tracking=True,
    )
    salesperson_id = fields.Many2one('res.users', string='Salesperson', tracking=True)
    receipt_amount = fields.Monetary(
        string='Full Receipt Amount',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    commission_rate = fields.Float(
        string='Commission %',
        required=True,
        default=5.0,
        digits=(5, 2),
    )
    commission_amount = fields.Monetary(
        string='Commission Amount',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    vat_rate = fields.Float(
        string='VAT %',
        default=15.0,
        digits=(5, 2),
    )
    vat_amount = fields.Monetary(
        string='VAT Amount',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    total_invoice_amount = fields.Monetary(
        string='Amount to Invoice',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    subcontractor_payable = fields.Monetary(
        string='Subcontractor Payable',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('invoiced', 'Invoiced'),
            ('settled', 'Settled'),
        ],
        string='Status',
        default='draft',
        tracking=True,
        copy=False,
    )
    invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Invoice',
        readonly=True,
        copy=False,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
        store=True,
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
        domain="[('type', '=', 'sale'), ('company_id', '=', company_id)]",
        check_company=True,
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
    )
    subcontractor_bill_id = fields.Many2one(
        comodel_name='account.move',
        string='Subcontractor Vendor Bill',
        readonly=True,
        copy=False,
    )
    notes = fields.Text(string='Notes')
    period = fields.Char(string='Period/Reference')
    is_paid_to_subcontractor = fields.Boolean(
        string='Paid to Subcontractor',
        default=False,
        tracking=True,
    )
    subcontractor_payment_date = fields.Date(
        string='Payment Date to Subcontractor',
    )
    subcontractor_payment_ref = fields.Char(
        string='Payment Reference',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'way4tech.commission.receipt'
                ) or _('New')
        return super().create(vals_list)

    receipt_excl_vat = fields.Monetary(
        string='Receipt Ex-VAT',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id',
        help='Receipt amount excluding the embedded VAT (receipt / (1 + VAT%))',
    )

    @api.depends('receipt_amount', 'commission_rate', 'vat_rate')
    def _compute_amounts(self):
        for rec in self:
            # Commission is calculated on the ex-VAT portion of the receipt
            divisor = 1.0 + rec.vat_rate / 100.0
            excl_vat = rec.receipt_amount / divisor if divisor else rec.receipt_amount
            commission = excl_vat * rec.commission_rate / 100.0
            vat = commission * rec.vat_rate / 100.0
            total_invoice = commission + vat
            rec.receipt_excl_vat = excl_vat
            rec.commission_amount = commission
            rec.vat_amount = vat
            rec.total_invoice_amount = total_invoice
            rec.subcontractor_payable = rec.receipt_amount - total_invoice

    def action_confirm(self):
        self.ensure_one()
        self.state = 'confirmed'

    def action_create_invoice(self):
        self.ensure_one()
        if self.state not in ('confirmed',):
            raise UserError(_('Commission receipt must be confirmed before creating an invoice.'))

        # Find VAT tax for sales
        vat_tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('amount', '=', self.vat_rate),
            ('amount_type', '=', 'percent'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not vat_tax and self.vat_rate:
            raise UserError(_(
                'No %.0f%% sales tax found. Please create a sales tax with amount %.0f%% '
                'before creating the invoice, or set VAT %% to 0.'
            ) % (self.vat_rate, self.vat_rate))

        # Load settings for this company
        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)
        analytic = self.analytic_account_id or settings.default_analytic_account_id
        analytic_distribution = {str(analytic.id): 100} if analytic else {}

        invoice_line_vals = {
            'name': 'Commission - %s' % self.name,
            'quantity': 1.0,
            'price_unit': self.commission_amount,
        }
        if vat_tax:
            invoice_line_vals['tax_ids'] = [(6, 0, [vat_tax.id])]
        # Use commission income account from settings
        if settings.commission_income_account_id:
            invoice_line_vals['account_id'] = settings.commission_income_account_id.id
        if analytic_distribution:
            invoice_line_vals['analytic_distribution'] = analytic_distribution

        # Add period/reference if set
        if self.period:
            invoice_line_vals['name'] = '%s (%s)' % (
                invoice_line_vals['name'], self.period
            )

        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.subcontractor_id.id,
            'invoice_date': self.date,
            'company_id': self.company_id.id,
            'invoice_line_ids': [(0, 0, invoice_line_vals)],
            'narration': self.notes or '',
        }
        # Use commission journal from settings, then from record, then Odoo default
        journal = self.journal_id or settings.commission_journal_id
        if journal:
            invoice_vals['journal_id'] = journal.id

        _category = self.env.ref('way4tech_logistics.category_commission', raise_if_not_found=False)
        if _category:
            invoice_vals['way4tech_category_id'] = _category.id
        invoice = self.env['account.move'].create(invoice_vals)
        self.write({
            'invoice_id': invoice.id,
            'state': 'invoiced',
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_create_subcontractor_bill(self):
        """Create a vendor bill payable to the subcontractor for their cut (receipt - commission - VAT)."""
        self.ensure_one()
        if self.state != 'invoiced':
            raise UserError(_('Please create the commission invoice first.'))
        if self.subcontractor_bill_id:
            raise UserError(_('A vendor bill for this subcontractor already exists.'))

        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)
        analytic = self.analytic_account_id or settings.default_analytic_account_id
        analytic_distribution = {str(analytic.id): 100} if analytic else {}

        bill_line_vals = {
            'name': 'Subcontractor Payment - %s' % self.name,
            'quantity': 1.0,
            'price_unit': self.subcontractor_payable,
        }
        if self.period:
            bill_line_vals['name'] = '%s (%s)' % (bill_line_vals['name'], self.period)
        if settings.subcontractor_expense_account_id:
            bill_line_vals['account_id'] = settings.subcontractor_expense_account_id.id
        if analytic_distribution:
            bill_line_vals['analytic_distribution'] = analytic_distribution

        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.subcontractor_id.id,
            'invoice_date': self.date,
            'company_id': self.company_id.id,
            'invoice_line_ids': [(0, 0, bill_line_vals)],
            'narration': self.notes or '',
        }
        _category = self.env.ref('way4tech_logistics.category_commission', raise_if_not_found=False)
        if _category:
            bill_vals['way4tech_category_id'] = _category.id
        bill = self.env['account.move'].create(bill_vals)
        self.write({'subcontractor_bill_id': bill.id})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Subcontractor Vendor Bill'),
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_subcontractor_bill(self):
        self.ensure_one()
        if not self.subcontractor_bill_id:
            raise UserError(_('No vendor bill linked to this commission receipt.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Subcontractor Vendor Bill'),
            'res_model': 'account.move',
            'res_id': self.subcontractor_bill_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_settle(self):
        self.ensure_one()
        self.state = 'settled'

    def action_reset_draft(self):
        self.ensure_one()
        self.state = 'draft'

    def action_mark_subcontractor_paid(self):
        self.ensure_one()
        self.write({
            'is_paid_to_subcontractor': True,
            'subcontractor_payment_date': fields.Date.today(),
        })

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_('No invoice linked to this commission receipt.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
