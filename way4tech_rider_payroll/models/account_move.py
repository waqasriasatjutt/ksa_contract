# -*- coding: utf-8 -*-
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    rider_payroll_batch_id = fields.Many2one(
        comodel_name='rider.payroll.batch',
        string='Rider Payroll Batch',
        index=True,
        ondelete='set null',
        copy=False,
    )
