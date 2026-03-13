# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    commission_default_rate = fields.Float(
        string='Default Commission Rate (%)',
        related='company_id.commission_default_rate',
        readonly=False,
    )
    commission_liability_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Customer Deposit (Liability) Account',
        related='company_id.commission_liability_account_id',
        readonly=False,
        domain=[('account_type', 'in', ['liability_current', 'liability_payable'])],
    )
    commission_cash_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cash/Bank Account',
        related='company_id.commission_cash_account_id',
        readonly=False,
    )
    commission_income_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Commission Income Account',
        related='company_id.commission_income_account_id',
        readonly=False,
        domain=[('account_type', 'in', ['income', 'income_other'])],
    )
    commission_subcontractor_payable_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Subcontractor Payable Account',
        related='company_id.commission_subcontractor_payable_account_id',
        readonly=False,
        domain=[('account_type', 'in', ['liability_current', 'liability_payable'])],
    )
    commission_default_tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='Default VAT on Commission',
        related='company_id.commission_default_tax_id',
        readonly=False,
        domain=[('type_tax_use', '=', 'sale')],
    )
    commission_default_product_id = fields.Many2one(
        comodel_name='product.product',
        string='Default Commission Product',
        related='company_id.commission_default_product_id',
        readonly=False,
    )
    commission_receipt_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Default Receipt Journal',
        related='company_id.commission_receipt_journal_id',
        readonly=False,
        domain=[('type', 'in', ['bank', 'cash', 'general'])],
    )


class ResCompany(models.Model):
    _inherit = 'res.company'

    commission_default_rate = fields.Float(
        string='Default Commission Rate (%)',
        default=0.0,
    )
    commission_liability_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Customer Deposit Account',
        check_company=True,
    )
    commission_cash_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Cash/Bank Account',
        check_company=True,
    )
    commission_income_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Commission Income Account',
        check_company=True,
    )
    commission_subcontractor_payable_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Subcontractor Payable Account',
        check_company=True,
    )
    commission_default_tax_id = fields.Many2one(
        comodel_name='account.tax',
        string='Default VAT on Commission',
        check_company=True,
    )
    commission_default_product_id = fields.Many2one(
        comodel_name='product.product',
        string='Default Commission Product',
    )
    commission_receipt_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Default Receipt Journal',
        check_company=True,
    )
