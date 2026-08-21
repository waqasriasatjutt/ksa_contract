# -*- coding: utf-8 -*-
"""CR3-FINAL Part A point 9 — raise an approval request.

Redesigned (2026-08) into a 5-tab wizard. The underlying approval MECHANISM is
unchanged (who may approve, separation of duties, the requester ≠ approver rule
all still live in way4tech.manpower.approval.request). Only visibility,
categorisation and selection change:

  * Pending  (default) — the draft items still NEEDING approval, each with a
    checkbox; the user sends all / one / any subset, now or later. Below them,
    the contract's requests still awaiting a decision, for reference.
  * Approved / Rejected / Consumed / Orphaned — read-only tabs of the
    contract's requests by status.

An approved-but-unconsumed request is NEVER matched against or allowed to block
a brand-new one — that guard lives in _create_request; the wizard simply never
offers an already-in-flight item on the Pending tab.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.manpower_approval_request import GATED_MODELS


class Way4TechManpowerApprovalWizard(models.TransientModel):
    _name = 'way4tech.manpower.approval.wizard'
    _description = 'Manpower Contract — Send for Approval'

    contract_id = fields.Many2one(
        'way4tech.manpower.contract', string='Contract',
        required=True, readonly=True,
    )
    # Kept for the per-row entry point (default_mode='one'); the wizard now
    # always presents the full tabbed view regardless.
    mode = fields.Selection(
        [('all', "All of this contract's current drafts"),
         ('one', 'This item only')],
        default='all', required=True,
    )
    res_model = fields.Char()
    res_id = fields.Integer()
    approver_id = fields.Many2one('res.users', string='Approver', readonly=True)
    note = fields.Text(string='Note to Approver')
    urgent = fields.Boolean(
        string='Urgent',
        help='Flags the request as urgent for the approver. It never skips '
             'approval — nothing is created without one.',
    )

    # ── Pending tab: selectable items + existing undecided requests ───────
    pending_line_ids = fields.One2many(
        'way4tech.manpower.approval.wizard.line', 'wizard_id',
        string='Items Needing Approval',
    )
    pending_request_ids = fields.Many2many(
        'way4tech.manpower.approval.request',
        'w4t_appr_wiz_pending_rel', 'wiz_id', 'req_id',
        string='Awaiting a Decision', compute='_compute_request_tabs',
    )
    # ── Read-only status tabs ─────────────────────────────────────────────
    approved_request_ids = fields.Many2many(
        'way4tech.manpower.approval.request',
        'w4t_appr_wiz_approved_rel', 'wiz_id', 'req_id',
        string='Approved', compute='_compute_request_tabs',
    )
    rejected_request_ids = fields.Many2many(
        'way4tech.manpower.approval.request',
        'w4t_appr_wiz_rejected_rel', 'wiz_id', 'req_id',
        string='Rejected', compute='_compute_request_tabs',
    )
    consumed_request_ids = fields.Many2many(
        'way4tech.manpower.approval.request',
        'w4t_appr_wiz_consumed_rel', 'wiz_id', 'req_id',
        string='Consumed', compute='_compute_request_tabs',
    )
    orphaned_request_ids = fields.Many2many(
        'way4tech.manpower.approval.request',
        'w4t_appr_wiz_orphaned_rel', 'wiz_id', 'req_id',
        string='Orphaned', compute='_compute_request_tabs',
    )

    @staticmethod
    def _has_orphan(request):
        return any(request.line_ids.mapped('orphaned'))

    @api.depends('contract_id')
    def _compute_request_tabs(self):
        Request = self.env['way4tech.manpower.approval.request']
        for wiz in self:
            reqs = (Request.search([('contract_id', '=', wiz.contract_id.id)])
                    if wiz.contract_id else Request.browse())
            orphan = reqs.filtered(
                lambda r: r.state == 'cancelled' or self._has_orphan(r))
            live_no_orphan = reqs - orphan
            wiz.pending_request_ids = live_no_orphan.filtered(
                lambda r: r.state in ('pending', 'partial'))
            wiz.approved_request_ids = live_no_orphan.filtered(
                lambda r: r.state == 'approved')
            wiz.rejected_request_ids = live_no_orphan.filtered(
                lambda r: r.state == 'rejected')
            wiz.consumed_request_ids = live_no_orphan.filtered(
                lambda r: r.state == 'consumed')
            wiz.orphaned_request_ids = orphan

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        contract_id = res.get('contract_id') or self.env.context.get(
            'default_contract_id')
        if not contract_id:
            return res
        contract = self.env['way4tech.manpower.contract'].browse(contract_id)
        Request = self.env['way4tech.manpower.approval.request']
        try:
            res['approver_id'] = Request._get_configured_approver(
                contract.company_id).id
        except UserError:
            res['approver_id'] = False
        # Build the Pending-tab selectable items — only rows still needing
        # approval (never anything already awaiting/approved, so the wizard
        # cannot offer an item that would collide).
        mode = res.get('mode') or self.env.context.get('default_mode') or 'all'
        if mode == 'one':
            rm = res.get('res_model') or self.env.context.get('default_res_model')
            rid = res.get('res_id') or self.env.context.get('default_res_id')
            rec = self.env[rm].browse(rid).exists() if (rm and rid) else None
            items = ([rec] if (rec and not Request._way4tech_live_approval_line(rec))
                     else [])
        else:
            items = contract._collect_items_needing_approval()
        res['pending_line_ids'] = [(0, 0, {
            'res_model': rec._name,
            'res_id': rec.id,
            'item_name': Request._line_display_name(rec),
            'item_type': GATED_MODELS.get(rec._name, rec._name),
            'amount': Request._line_display_amount(rec),
            'selected': True,
        }) for rec in items]
        return res

    def action_send(self):
        self.ensure_one()
        contract = self.contract_id
        if contract.state != 'active':
            raise UserError(_(
                'Contract "%s" is not Active. Activate it before sending '
                'items for approval.'
            ) % contract.display_name)
        selected = self.pending_line_ids.filtered('selected')
        if not selected:
            raise UserError(_(
                'Tick at least one item on the Pending tab, then Send.'
            ))
        records = []
        for wl in selected:
            rec = self.env[wl.res_model].browse(wl.res_id).exists()
            if rec:
                records.append(rec)
        if not records:
            raise UserError(_('The selected items no longer exist.'))
        request = self.env['way4tech.manpower.approval.request']._create_request(
            contract, records, note=self.note, urgent=self.urgent,
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approval Request'),
            'res_model': 'way4tech.manpower.approval.request',
            'res_id': request.id,
            'view_mode': 'form',
            'target': 'current',
        }


class Way4TechManpowerApprovalWizardLine(models.TransientModel):
    _name = 'way4tech.manpower.approval.wizard.line'
    _description = 'Manpower Approval Wizard — Selectable Item'
    _order = 'item_type, id'

    wizard_id = fields.Many2one(
        'way4tech.manpower.approval.wizard', required=True, ondelete='cascade')
    selected = fields.Boolean(string='Send', default=True)
    res_model = fields.Char(required=True)
    res_id = fields.Integer(required=True)
    item_name = fields.Char(string='Item', readonly=True)
    item_type = fields.Char(string='Type', readonly=True)
    amount = fields.Float(string='Amount', readonly=True)
