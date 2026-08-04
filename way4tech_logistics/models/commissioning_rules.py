# -*- coding: utf-8 -*-
"""CB1 (19.0.4.0.0) — Commissioning Business configuration rule tables.

Two editable rate tables that live on the Payroll & Accounting Setup screen,
same pattern as the Manpower Sales Person Commission Rules — but kept SEPARATE
from Manpower so nothing there is touched or coupled.

* subcontractor rule — keyed on the subcontractor PARTNER: the commission
  AlZain keeps for lending its documents (percent of the ex-VAT amount, or a
  fix amount).
* salesperson rule — keyed on an EMPLOYEE: the referrer's cut. Two modes only,
  Fix Amount (once per client) and Gross Profit % (of the ~5% margin).
"""
from odoo import api, fields, models, _


class CommissioningSubcontractorRule(models.Model):
    _name = 'way4tech.commissioning.subcontractor.rule'
    _description = 'Commissioning Subcontractor Commission Rule'
    _order = 'partner_id'

    settings_id = fields.Many2one(
        'way4tech.payroll.settings', required=True, ondelete='cascade')
    company_id = fields.Many2one(
        related='settings_id.company_id', store=True, readonly=True)
    partner_id = fields.Many2one(
        'res.partner', string='Subcontractor', required=True,
        domain=[('supplier_rank', '>', 0)])
    is_fix = fields.Boolean(
        string='Fix Amount',
        help='On: a fixed commission amount per settlement. Off: a percent of '
             'the ex-VAT receipt.')
    percent = fields.Float(
        string='Commission %', digits=(5, 2), default=5.0,
        help='Percent of the ex-VAT receipt kept as AlZain commission.')
    fix_amount = fields.Monetary(
        string='Fix Amount', currency_field='currency_id')
    currency_id = fields.Many2one(
        related='company_id.currency_id', readonly=True)

    _sql_constraints = [
        ('settings_partner_unique', 'unique(settings_id, partner_id)',
         'One commission rule per subcontractor per company.'),
    ]

    def _resolve(self, excl_vat_base):
        """Commission amount for an ex-VAT base under this rule."""
        self.ensure_one()
        if self.is_fix:
            return self.fix_amount or 0.0
        return (excl_vat_base or 0.0) * (self.percent or 0.0) / 100.0


class CommissioningSalespersonRule(models.Model):
    _name = 'way4tech.commissioning.salesperson.rule'
    _description = 'Commissioning Salesperson Commission Rule'
    _order = 'employee_id'

    settings_id = fields.Many2one(
        'way4tech.payroll.settings', required=True, ondelete='cascade')
    company_id = fields.Many2one(
        related='settings_id.company_id', store=True, readonly=True)
    employee_id = fields.Many2one(
        'hr.employee', string='Salesperson', required=True)
    mode = fields.Selection(
        selection=[('fix', 'Fix Amount'), ('gp_percent', 'Gross Profit %')],
        string='Mode', required=True, default='gp_percent',
        help='Fix Amount: a set amount once per client, NOT multiplied by the '
             'invoice count. Gross Profit %: a percent of the realised gross '
             'profit (the AlZain commission).')
    percent = fields.Float(
        string='Gross Profit %', digits=(5, 2),
        help='Used when Mode = Gross Profit %.')
    fix_amount = fields.Monetary(
        string='Fix Amount', currency_field='currency_id',
        help='Used when Mode = Fix Amount. Applied once per client.')
    currency_id = fields.Many2one(
        related='company_id.currency_id', readonly=True)

    _sql_constraints = [
        ('settings_employee_unique', 'unique(settings_id, employee_id)',
         'One salesperson rule per employee per company.'),
    ]
