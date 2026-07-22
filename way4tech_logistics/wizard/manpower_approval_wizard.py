# -*- coding: utf-8 -*-
"""CR3-FINAL Part A point 9 — raise an approval request.

Two ways in, both required:
  * per row  — one item on its own, for urgent one-offs
  * header   — every current draft on the contract in a single request,
               the normal monthly cycle

Either way the resulting approval covers exactly the rows listed, is bound to
them by (model, id), and is consumed the moment they are acted on.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class Way4TechManpowerApprovalWizard(models.TransientModel):
    _name = 'way4tech.manpower.approval.wizard'
    _description = 'Manpower Contract — Send for Approval'

    contract_id = fields.Many2one(
        'way4tech.manpower.contract', string='Contract',
        required=True, readonly=True,
    )
    mode = fields.Selection(
        [('all', "All of this contract's current drafts"),
         ('one', 'This item only')],
        default='all', required=True,
    )
    res_model = fields.Char()
    res_id = fields.Integer()
    summary = fields.Text(string='Items', readonly=True)
    approver_id = fields.Many2one('res.users', string='Approver', readonly=True)
    note = fields.Text(string='Note to Approver')
    urgent = fields.Boolean(
        string='Urgent',
        help='Flags the request as urgent for the approver. It never skips '
             'approval — nothing is created without one.',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        contract_id = res.get('contract_id') or self.env.context.get(
            'default_contract_id')
        if not contract_id:
            return res
        contract = self.env['way4tech.manpower.contract'].browse(contract_id)
        try:
            res['approver_id'] = self.env[
                'way4tech.manpower.approval.request'
            ]._get_configured_approver(contract.company_id).id
        except UserError:
            res['approver_id'] = False
        records = self._resolve_records(contract, res.get('mode') or 'all',
                                        res.get('res_model'), res.get('res_id'))
        res['summary'] = '\n'.join(
            '• %s' % r.display_name for r in records
        ) or _('Nothing is waiting for approval.')
        return res

    @api.model
    def _resolve_records(self, contract, mode, res_model, res_id):
        if mode == 'one' and res_model and res_id:
            rec = self.env[res_model].browse(res_id).exists()
            return rec
        items = contract._collect_pending_items()
        if not items:
            return self.env['way4tech.manpower.contract'].browse()
        return items

    def action_send(self):
        self.ensure_one()
        contract = self.contract_id
        if contract.state != 'active':
            raise UserError(_(
                'Contract "%s" is not Active. Activate it before sending '
                'items for approval.'
            ) % contract.display_name)
        records = self._resolve_records(
            contract, self.mode, self.res_model, self.res_id)
        if not records:
            raise UserError(_('There is nothing waiting for approval.'))
        # A list of heterogeneous records — send them one model at a time so
        # the request lines carry the right (model, id) binding.
        Request = self.env['way4tech.manpower.approval.request']
        if isinstance(records, list):
            flat = records
        else:
            flat = [r for r in records]
        request = Request._create_request(
            contract, flat, note=self.note, urgent=self.urgent,
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approval Request'),
            'res_model': 'way4tech.manpower.approval.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }
