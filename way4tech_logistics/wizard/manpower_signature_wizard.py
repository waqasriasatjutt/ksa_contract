# -*- coding: utf-8 -*-
"""CR3-FINAL P12 — "Send for Signature" popup.

Before this, the header button opened a whole new full-page Signature Request
form in draft, and the accountant then had to click a second button on that
page to actually submit it. Two screens and two clicks for one intent.

Now: the button opens this small dialog with the Month already filled in, and
Confirm creates the request straight in *Pending* state. The line appears in
the contract's Approvals tab immediately — nobody types "Add a line".

Separation of duties: this wizard can only ever SEND. Approving is not
possible from the contract; it happens in the Manpower Approvals area by a
Logistics Manager, and ``action_approve`` re-checks that group server-side.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class Way4TechManpowerSignatureWizard(models.TransientModel):
    _name = 'way4tech.manpower.signature.wizard'
    _description = 'Manpower Contract — Send for Signature'

    contract_id = fields.Many2one(
        'way4tech.manpower.contract', string='Contract',
        required=True, readonly=True,
    )
    month = fields.Char(
        string='Month (MM/YYYY)', required=True,
        help='The contract-month this approval covers. Create Invoice and '
             'Create Bill stay locked for this month until it is approved.',
    )
    notes = fields.Text(
        string='Note to Approver',
        help='Optional context for whoever reviews this month.',
    )

    @api.model
    def default_get(self, fields_list):
        """Pre-fill Month from the contract's own period, falling back to
        today — so the accountant normally confirms without typing anything."""
        res = super().default_get(fields_list)
        contract_id = res.get('contract_id') or self.env.context.get(
            'default_contract_id',
        )
        if contract_id and 'month' in fields_list and not res.get('month'):
            contract = self.env['way4tech.manpower.contract'].browse(contract_id)
            source = contract.start_date or fields.Date.context_today(self)
            res['month'] = source.strftime('%m/%Y')
        return res

    def action_confirm(self):
        """Create the request already submitted (state='pending')."""
        self.ensure_one()
        existing = self.env['way4tech.manpower.contract.signature.request'].search([
            ('contract_id', '=', self.contract_id.id),
            ('month', '=', self.month),
            ('state', '!=', 'cancelled'),
        ], limit=1)
        if existing:
            raise UserError(_(
                'A signature request for %(month)s already exists on this '
                'contract and is currently "%(state)s". Cancel it before '
                'sending a new one.'
            ) % {
                'month': self.month,
                'state': dict(existing._fields['state'].selection).get(
                    existing.state, existing.state,
                ),
            })
        request = self.env['way4tech.manpower.contract.signature.request'].create({
            'contract_id': self.contract_id.id,
            'month': self.month,
            'notes': self.notes or False,
        })
        # Straight to pending — snapshot captured on the way, exactly as the
        # two-step flow did, minus the second click.
        request.action_confirm_pending()
        request.message_post(body=_(
            'Sent for signature by %(user)s. Awaiting approval in Manpower '
            'Approvals.'
        ) % {'user': self.env.user.display_name})
        return {'type': 'ir.actions.act_window_close'}
