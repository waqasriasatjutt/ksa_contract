# -*- coding: utf-8 -*-
"""CR2 G3 (19.0.2.7.0) — per-employee salesperson commission rate table.

One row per hr.employee per company (unique). Referenced by
``way4tech.manpower.contract._get_commission_amount`` when computing the
commission on a Sales Person Commission line, based on the contract's
``commission_type`` Selection.

Rates are stored as PERCENT values (2.0 == 2%), not fractions —
keeps the settings screen readable for accountants.
"""
from odoo import fields, models


class Way4TechCommissionTemplate(models.Model):
    _name = 'way4tech.commission.template'
    _description = 'Sales Person Commission Template'
    _rec_name = 'employee_id'
    _order = 'employee_id'

    settings_id = fields.Many2one(
        'way4tech.payroll.settings', ondelete='cascade',
        help='Back-reference to the settings record that owns this template row.',
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Salesperson', required=True, ondelete='cascade',
        help='Internal HR employee. A single template is allowed per employee '
             'per company — commission-line lookups on manpower contracts '
             'read the rate columns from THIS row for the picked commission_type.',
    )
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', readonly=True, store=True,
    )
    fix_rate = fields.Monetary(
        string='Fix Amount / Invoice', currency_field='currency_id',
        help='Flat monetary amount paid per POSTED customer invoice generated '
             'in the target month (drafts + credit notes excluded). Used when '
             "the contract's commission_type is \"fix\".",
    )
    gp_rate = fields.Float(
        string='Gross Profit %', digits=(6, 2),
        help='Percentage (e.g. 2.0 == 2%) of Project Gross Profit paid as '
             'commission when contract commission_type is "gp". '
             'Gated: no payout unless Actual Profit > 0.',
    )
    np_rate = fields.Float(
        string='Net Profit %', digits=(6, 2),
        help='Percentage of Project Net Profit paid as commission when '
             'contract commission_type is "np". Gated on Actual Profit > 0.',
    )
    budgeted_rate = fields.Float(
        string='Budgeted Profit %', digits=(6, 2),
        help='Percentage of Budgeted Profit paid as commission when contract '
             'commission_type is "budgeted". Gated on Actual Profit > 0.',
    )
    actual_rate = fields.Float(
        string='Actual Profit %', digits=(6, 2),
        help='Percentage of Actual Profit paid as commission when contract '
             'commission_type is "actual". Gated on Actual Profit > 0.',
    )

    _sql_constraints = [(
        'employee_company_unique',
        'UNIQUE(employee_id, company_id)',
        'Only one commission template per employee per company is allowed.',
    )]
