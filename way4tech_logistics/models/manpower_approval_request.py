# -*- coding: utf-8 -*-
"""CR3-FINAL Part A — approval that covers ONE thing, ONCE.

The old gate matched on (contract, month). Once any request for a contract-month
was approved, every subsequent document on that contract sailed through
unchallenged — which is what testing hit on devnew: contract 36 was approved for
07/2026 at 05:42, and everything created afterwards was silently unlocked.

The rule now:

  * An approval is bound to a SPECIFIC ROW on a SPECIFIC CONTRACT, by model name
    and database id. It is never matched by client, by month, or by contract
    alone, so an approval on one contract cannot unlock another contract, a later
    row, or a future month.
  * An approval is CONSUMED the moment it is acted on. Creating the document
    burns it. Nothing stays open.
  * Editing an approved row invalidates its approval — the amount that was
    signed off is the amount that must post.
  * A request may cover several rows at once (the normal monthly cycle), but once
    that request is approved or rejected it closes. Anything created afterwards
    needs a fresh one.
  * The requester can never approve their own work.

Signing happens in the Odoo Sign module; this model owns the state machine and
the gate, and carries the link to the sign.request.
"""
import hashlib

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

# Every gated action: model → (label, the field holding the created document)
GATED_MODELS = {
    'way4tech.manpower.invoice.block': 'Invoice Block',
    'way4tech.manpower.contract.income.line': 'Project Income',
    'way4tech.manpower.timesheet': 'Timesheet',
    'way4tech.manpower.project.expense': 'Project Expense',
    'way4tech.manpower.commission.line': 'Sales Person Commission',
    'way4tech.manpower.contract.budget.line': 'Project Budget',
}


class Way4TechManpowerApprovalRequest(models.Model):
    _name = 'way4tech.manpower.approval.request'
    _description = 'Manpower Contract — Approval Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'

    name = fields.Char(string='Reference', compute='_compute_name', store=True)
    contract_id = fields.Many2one(
        'way4tech.manpower.contract', string='Contract',
        required=True, ondelete='cascade', index=True, tracking=True,
    )
    company_id = fields.Many2one(
        related='contract_id.company_id', store=True, readonly=True,
    )
    line_ids = fields.One2many(
        'way4tech.manpower.approval.request.line', 'request_id',
        string='Items', help='The exact rows this approval covers.',
    )
    line_count = fields.Integer(compute='_compute_line_count', store=True)
    state = fields.Selection(
        selection=[
            ('pending', 'Pending Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            ('consumed', 'Consumed'),
            ('cancelled', 'Cancelled'),
        ],
        default='pending', tracking=True, copy=False,
        help='Approved means the covered rows may be created ONCE. As soon as '
             'they are, the request moves to Consumed and unlocks nothing '
             'further.',
    )
    approver_id = fields.Many2one(
        'res.users', string='Approver', tracking=True, readonly=True,
        help='Taken from Payroll & Accounting Setup when the request is sent. '
             'The requester is never allowed to be the approver.',
    )
    requested_by = fields.Many2one(
        'res.users', string='Requested By', readonly=True, copy=False,
        default=lambda self: self.env.user,
    )
    decided_on = fields.Datetime(string='Decided On', readonly=True, copy=False)
    reason = fields.Text(
        string='Reason', tracking=True,
        help='Mandatory when rejecting or returning for correction.',
    )
    note = fields.Text(string='Note to Approver')
    sign_request_id = fields.Many2one(
        'sign.request', string='Sign Request', readonly=True, copy=False,
    )
    urgent = fields.Boolean(
        string='Urgent',
        help='Fast-track flag for the approver. It never skips approval — '
             'nothing is created without one.',
    )

    @api.depends('contract_id.name', 'contract_id.reference', 'create_date')
    def _compute_name(self):
        # CR3-FINAL Part A point 15: named from the contract, NOT from an
        # invoice number — at approval time no document exists yet.
        for rec in self:
            c = rec.contract_id
            month = c.start_date.strftime('%m/%Y') if c.start_date else ''
            rec.name = ' — '.join(p for p in (
                c.reference or '', c.client_id.display_name or '', month,
                _('Approval #%s') % (rec.id or 'new'),
            ) if p)

    @api.depends('line_ids')
    def _compute_line_count(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)

    # ── The gate ──────────────────────────────────────────────────────────
    @api.model
    def _require_approval(self, record):
        """Raise unless `record` has a live, matching, unconsumed approval.

        Matching is by (model, id) — never by client, month or contract.
        """
        contract = record.contract_id
        if not contract:
            raise UserError(_('This row is not linked to a contract.'))
        # Part A point 4: the contract itself must be Active.
        if contract.state != 'active':
            raise UserError(_(
                'Contract "%(name)s" is %(state)s. Activate the contract '
                'before creating invoices or bills.'
            ) % {
                'name': contract.display_name,
                'state': dict(
                    contract._fields['state'].selection,
                ).get(contract.state, contract.state),
            })
        line = self.env['way4tech.manpower.approval.request.line'].search([
            ('res_model', '=', record._name),
            ('res_id', '=', record.id),
            ('request_id.state', '=', 'approved'),
            ('consumed', '=', False),
        ], limit=1)
        if not line:
            raise UserError(_(
                'No approval for this item.\n\n'
                'Every invoice, bill and line needs its own approval, even '
                'within the same contract and month — approving one item '
                'never unlocks another. Click "Send for Approval" on this row '
                '(or on the contract header to send all current drafts at '
                'once), then have the authorised approver sign it.'
            ))
        # Part A point 14: the figures signed off must be the figures posted.
        if line.fingerprint != line._build_fingerprint(record):
            raise UserError(_(
                'This item changed after it was approved, so the approval is '
                'no longer valid. Send it for approval again.'
            ))
        return line

    @api.model
    def _consume_approval(self, record):
        """Burn the approval. Called immediately after the document exists."""
        line = self.env['way4tech.manpower.approval.request.line'].search([
            ('res_model', '=', record._name),
            ('res_id', '=', record.id),
            ('request_id.state', '=', 'approved'),
            ('consumed', '=', False),
        ], limit=1)
        if not line:
            return False
        line.consumed = True
        request = line.request_id
        request.message_post(body=_(
            'Approval consumed by %(item)s.'
        ) % {'item': record.display_name})
        # Once every covered row has been acted on, the request closes.
        if all(request.line_ids.mapped('consumed')):
            request.state = 'consumed'
        return True

    @api.model
    def _invalidate_for(self, records):
        """Drop any live approval covering these rows — used when a row is
        edited, or when its document is reset to draft (Part A point 13)."""
        if not records:
            return
        lines = self.env['way4tech.manpower.approval.request.line'].search([
            ('res_model', '=', records._name),
            ('res_id', 'in', records.ids),
            ('request_id.state', '=', 'approved'),
            ('consumed', '=', False),
        ])
        for line in lines:
            line.request_id.message_post(body=_(
                'Approval invalidated — %(item)s changed after approval.'
            ) % {'item': line.display_name})
            line.request_id.state = 'cancelled'

    # ── Workflow ──────────────────────────────────────────────────────────
    @api.model
    def _get_configured_approver(self, company):
        settings = self.env['way4tech.payroll.settings'].get_for_company(company.id)
        approver = settings.manpower_approver_id
        if not approver:
            raise UserError(_(
                'No Approver configured. Set one in Configuration → Payroll & '
                'Accounting Setup → Manpower Contracts → Approver.'
            ))
        return approver

    @api.model
    def _create_request(self, contract, records, note=False, urgent=False):
        """Raise ONE request covering `records` (one row, or a month's worth)."""
        if not records:
            raise UserError(_('There is nothing waiting for approval.'))
        approver = self._get_configured_approver(contract.company_id)
        # Part A point 7: self-approval is refused up front, not at sign time.
        if approver == self.env.user:
            raise UserError(_(
                'You are the configured Approver, so you cannot submit this '
                'for your own approval. Ask another authorised user to '
                'approve it, or change the Approver in Payroll & Accounting '
                'Setup.'
            ))
        Line = self.env['way4tech.manpower.approval.request.line']
        request = self.create({
            'contract_id': contract.id,
            'approver_id': approver.id,
            'note': note or False,
            'urgent': urgent,
        })
        for rec in records:
            existing = Line.search([
                ('res_model', '=', rec._name), ('res_id', '=', rec.id),
                ('consumed', '=', False),
                ('request_id.state', 'in', ('pending', 'approved')),
            ], limit=1)
            if existing:
                raise UserError(_(
                    '"%(item)s" is already on approval request %(req)s.'
                ) % {'item': rec.display_name,
                     'req': existing.request_id.name or existing.request_id.id})
            Line.create({
                'request_id': request.id,
                'res_model': rec._name,
                'res_id': rec.id,
                'description': rec.display_name,
                'amount': getattr(rec, 'amount_total', False)
                or getattr(rec, 'amount', 0.0) or 0.0,
                'fingerprint': Line._build_fingerprint(rec),
            })
        request._launch_sign_request()
        return request

    def _launch_sign_request(self):
        """Hand the request to the Sign module if a template is configured.

        Sign is optional plumbing, not the gate. If no template is set the
        approval still works end to end through this model — the approver
        just approves from Manpower → Approvals instead of signing a PDF.
        """
        self.ensure_one()
        settings = self.env['way4tech.payroll.settings'].get_for_company(
            self.company_id.id,
        )
        template = getattr(settings, 'manpower_sign_template_id', False)
        if not template or 'sign.request' not in self.env:
            return False
        try:
            sign_request = self.env['sign.request'].create({
                'template_id': template.id,
                'reference': self.name,
                'request_item_ids': [(0, 0, {
                    'partner_id': self.approver_id.partner_id.id,
                    'role_id': template.sign_item_ids[:1].responsible_id.id or False,
                })],
            })
            self.sign_request_id = sign_request.id
        except Exception as exc:            # noqa: BLE001 - never block the gate
            self.message_post(body=_(
                'Could not raise a Sign request automatically (%s). Approve '
                'from Manpower → Approvals instead.'
            ) % exc)
        return True

    def action_approve(self):
        for rec in self:
            if rec.state != 'pending':
                raise UserError(_('Only a Pending request can be approved.'))
            if not self.env.user.has_group(
                    'way4tech_logistics.group_logistics_manager'):
                raise UserError(_(
                    'Only a Logistics Manager can approve. Approvals are '
                    'granted in Manpower → Approvals, never from the contract.'
                ))
            if rec.requested_by == self.env.user:
                raise UserError(_(
                    'You submitted this request, so you cannot approve it. '
                    'Separation of duties requires a different approver.'
                ))
            rec.write({'state': 'approved', 'decided_on': fields.Datetime.now()})
        return True

    def action_reject(self):
        for rec in self:
            if rec.state != 'pending':
                raise UserError(_('Only a Pending request can be rejected.'))
            if not rec.reason:
                raise UserError(_(
                    'Enter a reason before rejecting — the requester needs to '
                    'know what to correct.'
                ))
            rec.write({'state': 'rejected', 'decided_on': fields.Datetime.now()})
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state == 'consumed':
                raise UserError(_(
                    'This approval has already been acted on and cannot be '
                    'cancelled.'
                ))
            rec.state = 'cancelled'
        return True

    def action_view_items(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approval Items'),
            'res_model': 'way4tech.manpower.approval.request.line',
            'view_mode': 'list',
            'domain': [('request_id', '=', self.id)],
        }


class Way4TechManpowerApprovalMixin(models.AbstractModel):
    """Adds the per-row Send-for-Approval button and its status flag.

    Mixed into all six gated models so the button, the wording and the rules
    are identical everywhere — Part A point 2.
    """
    _name = 'way4tech.manpower.approval.mixin'
    _description = 'Manpower Approval Mixin'

    approval_state = fields.Selection(
        selection=[
            ('none', 'Not Sent'),
            ('pending', 'Awaiting Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Approval', compute='_compute_approval_state',
        help='Approval status of THIS row. Each row is approved on its own; '
             'approving one never unlocks another.',
    )

    def _compute_approval_state(self):
        Line = self.env['way4tech.manpower.approval.request.line']
        for rec in self:
            line = Line.search([
                ('res_model', '=', rec._name),
                ('res_id', '=', rec.id),
                ('consumed', '=', False),
                ('request_id.state', 'in', ('pending', 'approved', 'rejected')),
            ], order='id desc', limit=1)
            if not line:
                rec.approval_state = 'none'
            else:
                rec.approval_state = line.request_id.state

    def action_send_for_approval(self):
        """Raise a request covering just this row (Part A point 9, per-item)."""
        self.ensure_one()
        if not self.contract_id:
            raise UserError(_('This row is not linked to a contract.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send for Approval'),
            'res_model': 'way4tech.manpower.approval.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_contract_id': self.contract_id.id,
                'default_mode': 'one',
                'default_res_model': self._name,
                'default_res_id': self.id,
            },
        }

    def write(self, vals):
        """Part A point 14: editing an approved row voids its approval."""
        result = super().write(vals)
        watched = {'amount', 'amount_total', 'quantity', 'price', 'hours',
                   'rate', 'budget_amount', 'description', 'line_ids'}
        if watched & set(vals) and not self.env.context.get(
                'way4tech_skip_approval_invalidation'):
            self.env['way4tech.manpower.approval.request']._invalidate_for(self)
        return result


class Way4TechManpowerApprovalRequestLine(models.Model):
    _name = 'way4tech.manpower.approval.request.line'
    _description = 'Manpower Approval — Covered Item'
    _order = 'id'

    request_id = fields.Many2one(
        'way4tech.manpower.approval.request', required=True,
        ondelete='cascade', index=True,
    )
    # The binding. (res_model, res_id) is the whole point: an approval points
    # at one row, not at a client, a month or a contract.
    res_model = fields.Char(string='Item Model', required=True, index=True)
    res_id = fields.Integer(string='Item ID', required=True, index=True)
    description = fields.Char(string='Item')
    item_type = fields.Char(string='Type', compute='_compute_item_type')
    amount = fields.Float(string='Amount')
    consumed = fields.Boolean(
        string='Consumed', default=False, copy=False,
        help='Set the moment the approved document is created. A consumed '
             'line can never unlock anything again.',
    )
    fingerprint = fields.Char(
        string='Fingerprint', readonly=True,
        help='Hash of the figures at approval time. If the row is edited '
             'afterwards the hash stops matching and the approval is void.',
    )

    def _compute_item_type(self):
        for line in self:
            line.item_type = GATED_MODELS.get(line.res_model, line.res_model)

    @api.model
    def _build_fingerprint(self, record):
        """Hash the fields that must not change between approval and posting."""
        parts = [record._name, str(record.id)]
        for fname in ('amount', 'amount_total', 'amount_untaxed', 'quantity',
                      'price', 'hours', 'rate', 'budget_amount', 'description'):
            if fname in record._fields:
                parts.append('%s=%s' % (fname, record[fname]))
        if 'line_ids' in record._fields:
            for sub in record.line_ids:
                parts.append('L%s:%s' % (sub.id, getattr(sub, 'amount', '')))
        return hashlib.sha256('|'.join(parts).encode()).hexdigest()

    @api.constrains('res_model')
    def _check_model_allowed(self):
        for line in self:
            if line.res_model not in GATED_MODELS:
                raise ValidationError(_(
                    'Approvals cannot be raised for model "%s".'
                ) % line.res_model)

    def _get_record(self):
        self.ensure_one()
        if self.res_model not in self.env:
            return None
        return self.env[self.res_model].browse(self.res_id).exists()
