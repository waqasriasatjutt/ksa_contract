# -*- coding: utf-8 -*-
"""CR4 item 7 — confirm creating a zero-amount vendor bill.

A dialog, not a UserError: the user can proceed or cancel. On proceed it
re-calls action_create_bill with the skip flag so the bill is created
normally.
"""
from odoo import _, fields, models


class Way4TechZeroBillConfirmWizard(models.TransientModel):
    _name = 'way4tech.zero.bill.confirm.wizard'
    _description = 'Confirm Zero-Amount Vendor Bill'

    expense_id = fields.Many2one(
        'way4tech.manpower.project.expense', string='Expense Line',
        required=True, readonly=True,
    )
    message = fields.Char(compute='_compute_message')

    def _compute_message(self):
        for wiz in self:
            wiz.message = _(
                'This expense line has an amount of 0.00. Create the vendor '
                'bill anyway?'
            )

    def action_confirm(self):
        self.ensure_one()
        return self.expense_id.with_context(
            way4tech_skip_zero_bill_check=True,
        ).action_create_bill()
