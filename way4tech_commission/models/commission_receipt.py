# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.fields import Command
from odoo.exceptions import UserError, ValidationError


class CommissionReceipt(models.Model):
    _name = 'commission.receipt'
    _description = 'Commission Receipt'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, name desc'
    _check_company_auto = True

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Customer',
        required=True,
        tracking=True,
        help='The customer who made the full payment',
    )
    subcontractor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Subcontractor',
        tracking=True,
        help='The subcontractor who provided the service (will receive total minus commission)',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        readonly=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('invoiced', 'Commission Invoiced'),
            ('settled', 'Settled'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        copy=False,
        tracking=True,
    )

    # Financial fields
    total_amount = fields.Monetary(
        string='Total Amount Received',
        required=True,
        tracking=True,
        help='Full amount received from the customer (including VAT if applicable)',
    )
    vat_included = fields.Boolean(
        string='Amount Includes VAT',
        default=True,
        help='Check if the total amount already includes VAT',
    )
    vat_rate = fields.Float(
        string='VAT Rate (%)',
        default=15.0,
        help='VAT rate applied to the full amount (KSA standard is 15%)',
    )
    vat_amount = fields.Monetary(
        string='VAT Amount',
        compute='_compute_financial_fields',
        store=True,
        readonly=False,
        help='VAT portion of the total amount',
    )
    amount_excl_vat = fields.Monetary(
        string='Amount (Excl. VAT)',
        compute='_compute_financial_fields',
        store=True,
    )
    commission_rate = fields.Float(
        string='Commission Rate (%)',
        required=True,
        tracking=True,
        help='Commission percentage applied on amount excluding VAT',
    )
    commission_amount = fields.Monetary(
        string='Commission Amount',
        compute='_compute_financial_fields',
        store=True,
    )
    commission_vat_amount = fields.Monetary(
        string='VAT on Commission',
        compute='_compute_financial_fields',
        store=True,
        help='VAT applied only on the commission portion',
    )
    commission_total = fields.Monetary(
        string='Commission + VAT',
        compute='_compute_financial_fields',
        store=True,
    )
    subcontractor_payable = fields.Monetary(
        string='Subcontractor Payable',
        compute='_compute_financial_fields',
        store=True,
        help='Amount payable to subcontractor = Total - Commission - VAT on commission',
    )

    # Analytic
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        check_company=True,
        tracking=True,
    )

    # Accounting configuration
    receipt_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Receipt Journal',
        check_company=True,
        domain=[('type', 'in', ['bank', 'cash', 'general'])],
        tracking=True,
        help='Journal used to record the full receipt',
    )
    liability_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Customer Deposit Account',
        check_company=True,
        tracking=True,
        help='Liability account to record the full customer receipt (Cr)',
    )
    cash_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cash/Bank Account',
        check_company=True,
        tracking=True,
        help='Cash or bank account (Dr) when recording receipt',
    )
    commission_income_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Commission Income Account',
        check_company=True,
        tracking=True,
        help='Revenue account for commission income',
    )
    subcontractor_payable_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Subcontractor Payable Account',
        check_company=True,
        tracking=True,
        help='Payable account for amounts owed to subcontractors',
    )
    commission_tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='VAT on Commission',
        domain=[('type_tax_use', '=', 'sale')],
        check_company=True,
        tracking=True,
        help='VAT tax applied only to the commission portion',
    )
    commission_product_id = fields.Many2one(
        comodel_name='product.product',
        string='Commission Product',
        tracking=True,
        help='Product used when generating the commission invoice',
    )

    # Document links
    receipt_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Receipt Journal Entry',
        readonly=True,
        copy=False,
    )
    commission_invoice_id = fields.Many2one(
        comodel_name='account.move',
        string='Commission Invoice',
        readonly=True,
        copy=False,
    )
    settlement_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Settlement Entry',
        readonly=True,
        copy=False,
    )

    # Detail lines (optional breakdown)
    line_ids = fields.One2many(
        comodel_name='commission.receipt.line',
        inverse_name='receipt_id',
        string='Breakdown',
    )
    notes = fields.Text(string='Notes')

    @api.depends('total_amount', 'vat_included', 'vat_rate', 'commission_rate', 'commission_tax_id')
    def _compute_financial_fields(self):
        for rec in self:
            total = rec.total_amount or 0.0
            vat_rate = (rec.vat_rate or 0.0) / 100.0

            if rec.vat_included and vat_rate > 0:
                amount_excl_vat = total / (1 + vat_rate)
                vat_amount = total - amount_excl_vat
            else:
                amount_excl_vat = total
                vat_amount = total * vat_rate

            commission_rate = (rec.commission_rate or 0.0) / 100.0
            commission_amount = amount_excl_vat * commission_rate

            # VAT on commission only
            commission_vat = 0.0
            if rec.commission_tax_id:
                commission_vat = commission_amount * (rec.commission_tax_id.amount / 100.0)
            commission_total = commission_amount + commission_vat

            # Subcontractor gets total minus commission (and its VAT)
            subcontractor_payable = total - commission_total

            rec.vat_amount = round(vat_amount, 2)
            rec.amount_excl_vat = round(amount_excl_vat, 2)
            rec.commission_amount = round(commission_amount, 2)
            rec.commission_vat_amount = round(commission_vat, 2)
            rec.commission_total = round(commission_total, 2)
            rec.subcontractor_payable = round(subcontractor_payable, 2)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('commission.receipt') or _('New')
        return super().create(vals_list)

    @api.onchange('company_id')
    def _onchange_company_id(self):
        company = self.company_id or self.env.company
        self.liability_account_id = company.commission_liability_account_id
        self.cash_account_id = company.commission_cash_account_id
        self.commission_income_account_id = company.commission_income_account_id
        self.subcontractor_payable_account_id = company.commission_subcontractor_payable_account_id
        self.commission_tax_id = company.commission_default_tax_id
        self.commission_product_id = company.commission_default_product_id
        self.receipt_journal_id = company.commission_receipt_journal_id
        self.commission_rate = company.commission_default_rate

    @api.constrains('total_amount', 'commission_rate', 'vat_rate')
    def _check_amounts(self):
        for rec in self:
            if rec.total_amount <= 0:
                raise ValidationError(_('Total amount must be greater than zero.'))
            if rec.commission_rate < 0 or rec.commission_rate > 100:
                raise ValidationError(_('Commission rate must be between 0 and 100%.'))
            if rec.vat_rate < 0 or rec.vat_rate > 100:
                raise ValidationError(_('VAT rate must be between 0 and 100%.'))

    def action_confirm(self):
        """Confirm receipt and create the liability journal entry."""
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only Draft receipts can be confirmed.'))
            rec._validate_accounting_config()
            rec._create_receipt_entry()
            rec.write({'state': 'confirmed'})
        return True

    def _validate_accounting_config(self):
        self.ensure_one()
        errors = []
        if not self.liability_account_id:
            errors.append(_('Customer Deposit Account is required.'))
        if not self.cash_account_id:
            errors.append(_('Cash/Bank Account is required.'))
        if not self.receipt_journal_id:
            errors.append(_('Receipt Journal is required.'))
        if errors:
            raise UserError('\n'.join(errors))

    def _create_receipt_entry(self):
        """Dr Cash/Bank | Cr Customer Deposit Liability for full amount."""
        self.ensure_one()
        analytic_distribution = {}
        if self.analytic_account_id:
            analytic_distribution = {str(self.analytic_account_id.id): 100.0}

        move_vals = {
            'move_type': 'entry',
            'journal_id': self.receipt_journal_id.id,
            'date': self.date,
            'ref': _('Receipt: %s – %s') % (self.name, self.partner_id.name),
            'company_id': self.company_id.id,
            'partner_id': self.partner_id.id,
            'line_ids': [
                Command.create({
                    'name': _('Customer Receipt – %s') % self.name,
                    'account_id': self.cash_account_id.id,
                    'debit': self.total_amount,
                    'credit': 0.0,
                    'partner_id': self.partner_id.id,
                    'analytic_distribution': analytic_distribution or False,
                }),
                Command.create({
                    'name': _('Customer Deposit – %s') % self.name,
                    'account_id': self.liability_account_id.id,
                    'debit': 0.0,
                    'credit': self.total_amount,
                    'partner_id': self.partner_id.id,
                    'analytic_distribution': analytic_distribution or False,
                }),
            ],
        }
        move = self.env['account.move'].sudo().create(move_vals)
        move._post(soft=False)
        self.receipt_move_id = move

    def action_generate_commission_invoice(self):
        """Generate a customer invoice for the commission amount with VAT."""
        for rec in self:
            if rec.state != 'confirmed':
                raise UserError(_('Receipt must be in Confirmed state to generate commission invoice.'))
            if rec.commission_invoice_id:
                raise UserError(_('Commission invoice already exists for this receipt.'))

            commission_journal = rec.env['account.journal'].search([
                *rec.env['account.journal']._check_company_domain(rec.company_id),
                ('type', '=', 'sale'),
            ], limit=1)
            if not commission_journal:
                raise UserError(_('No sales journal found. Please configure a sales journal.'))

            if not rec.commission_income_account_id:
                raise UserError(_('Commission Income Account is required to generate invoice.'))

            analytic_distribution = {}
            if rec.analytic_account_id:
                analytic_distribution = {str(rec.analytic_account_id.id): 100.0}

            line_vals = {
                'name': _('Commission – %s (%s%%)') % (rec.name, rec.commission_rate),
                'quantity': 1.0,
                'price_unit': rec.commission_amount,
                'account_id': rec.commission_income_account_id.id,
                'analytic_distribution': analytic_distribution or False,
            }
            if rec.commission_tax_id:
                line_vals['tax_ids'] = [Command.set([rec.commission_tax_id.id])]
            if rec.commission_product_id:
                line_vals['product_id'] = rec.commission_product_id.id

            invoice_vals = {
                'move_type': 'out_invoice',
                'journal_id': commission_journal.id,
                'invoice_date': rec.date,
                'partner_id': rec.partner_id.id,
                'ref': _('Commission – %s') % rec.name,
                'company_id': rec.company_id.id,
                'invoice_line_ids': [Command.create(line_vals)],
                'narration': _(
                    'Commission receipt: %s\nTotal received: %s\nCommission rate: %s%%'
                ) % (rec.name, rec.total_amount, rec.commission_rate),
            }
            invoice = rec.env['account.move'].sudo().create(invoice_vals)
            rec.commission_invoice_id = invoice
            rec.write({'state': 'invoiced'})

        return {
            'type': 'ir.actions.act_window',
            'name': _('Commission Invoice'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.commission_invoice_id.id,
        }

    def action_settle(self):
        """
        Settle the receipt:
        Dr Customer Deposit (full amount)
        Cr Commission Income (commission_amount)
        Cr VAT Payable (commission_vat_amount) — if not handled via invoice
        Cr Subcontractor Payable (subcontractor_payable)
        """
        for rec in self:
            if rec.state != 'invoiced':
                raise UserError(_('Receipt must be in Invoiced state to settle.'))
            if not rec.subcontractor_payable_account_id:
                raise UserError(_('Subcontractor Payable Account is required for settlement.'))
            if not rec.commission_income_account_id:
                raise UserError(_('Commission Income Account is required for settlement.'))

            analytic_distribution = {}
            if rec.analytic_account_id:
                analytic_distribution = {str(rec.analytic_account_id.id): 100.0}

            settlement_lines = [
                # Dr: Clear the liability
                Command.create({
                    'name': _('Settlement – Clear Deposit: %s') % rec.name,
                    'account_id': rec.liability_account_id.id,
                    'debit': rec.total_amount,
                    'credit': 0.0,
                    'partner_id': rec.partner_id.id,
                }),
                # Cr: Commission income
                Command.create({
                    'name': _('Commission Income – %s') % rec.name,
                    'account_id': rec.commission_income_account_id.id,
                    'debit': 0.0,
                    'credit': rec.commission_amount,
                    'analytic_distribution': analytic_distribution or False,
                }),
                # Cr: Subcontractor payable
                Command.create({
                    'name': _('Subcontractor Payable – %s') % rec.name,
                    'account_id': rec.subcontractor_payable_account_id.id,
                    'debit': 0.0,
                    'credit': rec.subcontractor_payable,
                    'partner_id': rec.subcontractor_id.id if rec.subcontractor_id else False,
                }),
            ]

            # If commission VAT is tracked here (not via the invoice)
            if rec.commission_vat_amount and not rec.commission_invoice_id:
                vat_account = rec.commission_tax_id.invoice_repartition_line_ids.filtered(
                    lambda l: l.repartition_type == 'tax'
                ).account_id[:1]
                if vat_account:
                    settlement_lines.append(Command.create({
                        'name': _('VAT on Commission – %s') % rec.name,
                        'account_id': vat_account.id,
                        'debit': 0.0,
                        'credit': rec.commission_vat_amount,
                    }))

            settlement_journal = rec.receipt_journal_id or rec.env['account.journal'].search([
                *rec.env['account.journal']._check_company_domain(rec.company_id),
                ('type', '=', 'general'),
            ], limit=1)

            move_vals = {
                'move_type': 'entry',
                'journal_id': settlement_journal.id,
                'date': fields.Date.today(),
                'ref': _('Settlement – %s') % rec.name,
                'company_id': rec.company_id.id,
                'line_ids': settlement_lines,
            }
            move = rec.env['account.move'].sudo().create(move_vals)
            move._post(soft=False)
            rec.settlement_move_id = move
            rec.write({'state': 'settled'})
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state in ('settled',):
                raise UserError(_('Settled receipts cannot be cancelled.'))
            if rec.receipt_move_id and rec.receipt_move_id.state == 'posted':
                raise UserError(
                    _('The receipt journal entry is already posted. '
                      'Please reverse it manually before cancelling.')
                )
            rec.write({'state': 'cancelled'})
        return True

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state == 'cancelled':
                rec.write({'state': 'draft'})
        return True

    def action_view_receipt_entry(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Receipt Entry'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.receipt_move_id.id,
        }

    def action_view_commission_invoice(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Commission Invoice'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.commission_invoice_id.id,
        }

    def action_view_settlement_entry(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Settlement Entry'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.settlement_move_id.id,
        }


class CommissionReceiptLine(models.Model):
    _name = 'commission.receipt.line'
    _description = 'Commission Receipt Line'
    _order = 'receipt_id, sequence'

    sequence = fields.Integer(string='Sequence', default=10)
    receipt_id = fields.Many2one(
        comodel_name='commission.receipt',
        string='Receipt',
        required=True,
        ondelete='cascade',
        index=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='receipt_id.currency_id',
        readonly=True,
    )
    description = fields.Char(string='Description', required=True)
    amount = fields.Monetary(string='Amount', required=True)
    note = fields.Char(string='Note')
