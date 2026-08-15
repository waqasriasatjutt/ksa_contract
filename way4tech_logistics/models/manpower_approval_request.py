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


def way4tech_first_real_change(record, vals, o2m_fields=None):
    """CR5 item 7 — the first field in ``vals`` that is a REAL user change to
    ``record``: a manual scalar whose value actually changes, or a command on a
    locked one2many / many2many. Computed and related fields, the ``state``
    field, and idempotent (same-value) writes are ignored — so stored-field
    recomputes and no-op saves pass straight through the Completed-lock guards.

    ``o2m_fields=None`` treats a command on ANY collection as an edit; pass a
    set/tuple to limit that to named collections (the contract passes its
    editable-line o2m set, so result links like ``invoice_ids`` are not counted
    as edits).
    """
    for fname, value in vals.items():
        field = record._fields.get(fname)
        if not field or fname == 'state':
            continue
        # System-maintained: computed-without-inverse and related fields are
        # written by the ORM (recompute), never by a user, so never block them.
        if (field.compute and not field.inverse) or field.related:
            continue
        if field.type in ('one2many', 'many2many'):
            if value and (o2m_fields is None or fname in o2m_fields):
                return fname
            continue
        current = record[fname]
        new_value = value
        if field.type == 'many2one':
            current = current.id if current else False
        elif field.type == 'date':
            new_value = fields.Date.to_date(value) if value else False
        elif field.type == 'datetime':
            new_value = fields.Datetime.to_datetime(value) if value else False
        if (new_value or False) != (current or False):
            return fname
    return None


# Every gated action: model → (label, the field holding the created document)
GATED_MODELS = {
    'way4tech.manpower.invoice.block': 'Invoice Block',
    # Item 4: the vendor-bill mirror of the invoice block — approved as one
    # item, exactly like the invoice block; its expense lines are billed via
    # the block, not individually.
    'way4tech.manpower.bill.block': 'Bill Block',
    'way4tech.manpower.timesheet.block': 'Timesheet Invoice Block',
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
            # CR3-FINAL round 3, item 3: a request can end up with some lines
            # approved and others rejected. It is not "approved" and it is not
            # "rejected" — it is both, and the approved lines are creatable.
            ('partial', 'Partly Approved'),
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
    # CR3-FINAL round 3, item 7: the pool who MAY decide this request. Any one
    # of them completes it; it is not a checklist.
    approver_ids = fields.Many2many(
        'res.users', 'way4tech_approval_request_approver_rel',
        'request_id', 'user_id', string='Approvers', readonly=True,
        help='Any one of these users can decide this request. Taken from '
             'Payroll & Accounting Setup when it is sent. The requester is '
             'excluded, so nobody can approve their own work.',
    )
    approver_id = fields.Many2one(
        'res.users', string='Decided By', tracking=True, readonly=True,
        help='Whoever actually approved or rejected it.',
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

    def _commit_decisions(self):
        """CR3-FINAL round 5, issue 3 — FINALIZE the request.

        Called ONLY by the three header buttons (Approve All / Reject All /
        Partially Approve). Per-row Approve/Reject are provisional markings
        that do NOT come through here, so a request stays open (Pending) and
        fully decidable until the approver deliberately commits — navigating
        away, switching windows or deciding one row never closes it.

        Rolls the committed per-line decisions into the request's final state:
          all approved            → approved
          all rejected            → rejected
          mix of approved+rejected → partial
        Once committed, approved rows are creatable and rejected rows go back
        to the requester (their source row stays Draft/editable, badged
        Rejected with the reason).
        """
        for req in self:
            if req.state != 'pending':
                continue
            decisions = req.line_ids.mapped('decision')
            approved = any(d == 'approved' for d in decisions)
            rejected = any(d == 'rejected' for d in decisions)
            if approved and rejected:
                new_state = 'partial'
            elif rejected:
                new_state = 'rejected'
            elif approved:
                new_state = 'approved'
            else:
                new_state = 'pending'          # nothing decided — stay open
            if new_state == 'pending':
                continue
            req.write({
                'state': new_state,
                'approver_id': self.env.user.id,
                'decided_on': fields.Datetime.now(),
            })
            n_ok = sum(1 for d in decisions if d == 'approved')
            n_no = sum(1 for d in decisions if d == 'rejected')
            req.message_post(body=_(
                'Decision committed by %(user)s: %(ok)s approved, %(no)s '
                'rejected.'
            ) % {'user': self.env.user.display_name, 'ok': n_ok, 'no': n_no})

    def _refresh_consumed_state(self):
        """After a document is created from an approved row, close the request
        to Consumed once every approved (actionable) line has been acted on.
        A rejected line is not waiting for anything."""
        for req in self:
            if req.state not in ('approved', 'partial'):
                continue
            actionable = req.line_ids.filtered(lambda l: l.decision == 'approved')
            if actionable and all(l.consumed for l in actionable):
                req.state = 'consumed'

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
        # CR3-FINAL round 3, item 3: a line is creatable when IT is approved —
        # either because the whole request was approved, or because the
        # approver ticked this one inside a partly-approved request. A line
        # individually rejected inside an approved request stays blocked.
        Line = self.env['way4tech.manpower.approval.request.line']
        line = Line.search([
            ('res_model', '=', record._name),
            ('res_id', '=', record.id),
            ('consumed', '=', False),
            ('request_id.state', 'in', ('approved', 'partial')),
            '|', ('decision', '=', 'approved'),
            '&', ('decision', '=', False), ('request_id.state', '=', 'approved'),
        ], limit=1)
        if not line:
            rejected = Line.search([
                ('res_model', '=', record._name), ('res_id', '=', record.id),
                ('decision', '=', 'rejected'),
            ], order='id desc', limit=1)
            if rejected:
                raise UserError(_(
                    'This item was REJECTED by %(who)s.\n\nReason: %(why)s\n\n'
                    'Correct it and send it for approval again.'
                ) % {'who': rejected.request_id.approver_id.display_name or '',
                     'why': rejected.reason or rejected.request_id.reason or '—'})
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
        Line = self.env['way4tech.manpower.approval.request.line']
        line = Line.search([
            ('res_model', '=', record._name),
            ('res_id', '=', record.id),
            ('consumed', '=', False),
            ('request_id.state', 'in', ('approved', 'partial')),
            '|', ('decision', '=', 'approved'),
            '&', ('decision', '=', False), ('request_id.state', '=', 'approved'),
        ], limit=1)
        if not line:
            return False
        line.consumed = True
        request = line.request_id
        request.message_post(body=_(
            'Approval consumed by %(item)s.'
        ) % {'item': record.display_name})
        # Closes to Consumed only when every approved line has been acted on;
        # a rejected line is not waiting for anything (issue 3).
        request._refresh_consumed_state()
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
    def _get_configured_approvers(self, company):
        """CR3-FINAL round 3, item 7: the configured approver POOL.

        Any one of them can decide a request. Falls back to the legacy
        single-approver field so a 3.4/3.5 configuration keeps working.
        """
        settings = self.env['way4tech.payroll.settings'].get_for_company(company.id)
        approvers = settings.manpower_approver_ids
        if not approvers and settings.manpower_approver_id:
            approvers = settings.manpower_approver_id
        if not approvers:
            raise UserError(_(
                'No Approvers configured. Set at least one in Configuration → '
                'Payroll & Accounting Setup → Manpower Contracts → Approvers.'
            ))
        return approvers

    @api.model
    def _get_configured_approver(self, company):
        """Back-compat shim — returns the first configured approver."""
        return self._get_configured_approvers(company)[:1]

    @api.model
    def _line_display_name(self, rec):
        """CR3-FINAL round 5, issue 6a: a readable item name for the approver.

        Timesheet and Budget rows have no `name`, so `rec.display_name` fell
        back to 'model,id' (e.g. 'way4tech.manpower.timesheet,34') — the
        approver was signing off items identified only by a database id.
        """
        if rec._name == 'way4tech.manpower.timesheet':
            when = rec.date or rec.start_date or ''
            parts = [rec.employee_id.name or _('Timesheet'), str(when) if when else '',
                     rec.description or '']
            return ' — '.join(p for p in parts if p)
        if rec._name == 'way4tech.manpower.contract.budget.line':
            parts = [_('Budget'), rec.category_id.name or '', rec.description or '']
            return ' — '.join(p for p in parts if p)
        return rec.display_name

    @api.model
    def _line_display_amount(self, rec):
        """CR3-FINAL round 4, item 2: the figure the approver is authorising.

        A budget line has neither `amount_total` nor `amount` — its value is
        `budget_amount` (the Actual is derived later from confirmed bills and
        is not what is being approved). The old `amount_total or amount`
        chain therefore showed 0.00 for every budget item. Resolve per model
        so blocks, invoices, timesheets, expenses, commission AND budgets all
        show the right number.
        """
        if rec._name == 'way4tech.manpower.contract.budget.line':
            return rec.budget_amount or 0.0
        for field in ('amount_total', 'amount', 'price_subtotal'):
            if field in rec._fields and rec[field]:
                return rec[field]
        return 0.0

    @api.model
    def _create_request(self, contract, records, note=False, urgent=False):
        """Raise ONE request covering `records` (one row, or a month's worth)."""
        if not records:
            raise UserError(_('There is nothing waiting for approval.'))
        approvers = self._get_configured_approvers(contract.company_id)
        # Part A point 7 / item 7: the requester is removed from the pool, so
        # self-approval is impossible even when they are a configured approver.
        eligible = approvers - self.env.user
        if not eligible:
            raise UserError(_(
                'You are the only configured Approver, so you cannot submit '
                'this for your own approval. Add a second approver in '
                'Configuration → Payroll & Accounting Setup → Manpower '
                'Contracts → Approvers.'
            ))
        Line = self.env['way4tech.manpower.approval.request.line']
        request = self.create({
            'contract_id': contract.id,
            'approver_ids': [(6, 0, eligible.ids)],
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
                'description': self._line_display_name(rec),
                'amount': self._line_display_amount(rec),
                'fingerprint': Line._build_fingerprint(rec),
            })
        request._launch_sign_request()
        return request

    def _launch_sign_request(self):
        """CR3-FINAL round 3, item 8 — route the request through Odoo Sign.

        The client confirmed the Enterprise dependency, so this is now the
        intended path: signing produces the signed PDF, the signer record and
        Sign's own audit trail. The signer is set automatically from the
        configured Approvers — the requester never picks one.

        If no template is configured we do NOT fail: the request stays
        decidable in Manpower → Approvals, so a mis-set template can never
        block invoicing outright.
        """
        self.ensure_one()
        settings = self.env['way4tech.payroll.settings'].get_for_company(
            self.company_id.id,
        )
        template = settings.manpower_sign_template_id
        if not template:
            self.message_post(body=_(
                'No Approval Sign Template configured, so no Sign request was '
                'raised. Decide this in Manpower → Approvals, or set a '
                'template in Payroll & Accounting Setup.'
            ))
            return False
        signers = self.approver_ids.filtered(lambda u: u.partner_id)
        if not signers:
            self.message_post(body=_(
                'No approver has a contact record, so no Sign request could '
                'be raised. Decide this in Manpower → Approvals.'
            ))
            return False
        try:
            roles = template.sign_item_ids.mapped('responsible_id')
            role = roles[:1]
            # One request item per eligible approver — any ONE signature
            # completes it (item 7), so they share the same role.
            items = [(0, 0, {
                'partner_id': user.partner_id.id,
                'role_id': role.id if role else False,
            }) for user in signers]
            sign_request = self.env['sign.request'].create({
                'template_id': template.id,
                'reference': self.name,
                'request_item_ids': items,
            })
            self.sign_request_id = sign_request.id
            self.message_post(body=_(
                'Sent to Sign as "%(ref)s" for %(who)s.'
            ) % {'ref': self.name,
                 'who': ', '.join(signers.mapped('display_name'))})
        except Exception as exc:            # noqa: BLE001 - never block the gate
            self.message_post(body=_(
                'Could not raise a Sign request automatically (%s). Decide '
                'this in Manpower → Approvals instead.'
            ) % exc)
        return True

    def action_open_sign_request(self):
        """Jump to the Sign document — the contract only shows status."""
        self.ensure_one()
        if not self.sign_request_id:
            raise UserError(_('No Sign request is linked to this approval.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sign Request'),
            'res_model': 'sign.request',
            'res_id': self.sign_request_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _check_may_decide(self):
        """Shared guard for every decision path."""
        self.ensure_one()
        if not self.env.user.has_group(
                'way4tech_logistics.group_logistics_manager'):
            raise UserError(_(
                'Only a Logistics Manager can approve. Approvals are granted '
                'in Manpower → Approvals, never from the contract.'
            ))
        if self.requested_by == self.env.user:
            raise UserError(_(
                'You submitted this request, so you cannot approve it. '
                'Separation of duties requires a different approver.'
            ))
        # Item 7: any ONE of the configured approvers may decide.
        if self.approver_ids and self.env.user not in self.approver_ids:
            raise UserError(_(
                'You are not one of the approvers for this request. It can be '
                'decided by: %s.'
            ) % ', '.join(self.approver_ids.mapped('display_name')))

    def action_approve(self):
        """Header button 'Approve All' — approve every row, then commit."""
        for rec in self:
            if rec.state != 'pending':
                raise UserError(_(
                    'This request has already been decided (%s).'
                ) % dict(rec._fields['state'].selection).get(rec.state))
            rec._check_may_decide()
            rec.line_ids.write({'decision': 'approved', 'reason': False})
            rec._commit_decisions()
        return True

    def action_reject(self):
        """Header button 'Reject All' — reject every row with one reason,
        then commit. The requester gets all rows back to correct and resend."""
        for rec in self:
            if rec.state != 'pending':
                raise UserError(_(
                    'This request has already been decided (%s).'
                ) % dict(rec._fields['state'].selection).get(rec.state))
            rec._check_may_decide()
            if not rec.reason:
                raise UserError(_(
                    'Enter a Reason before rejecting — the requester needs to '
                    'know what to correct.'
                ))
            rec.line_ids.write({'decision': 'rejected', 'reason': rec.reason})
            rec._commit_decisions()
        return True

    def action_partially_approve(self):
        """Header button 'Partially Approve' — commit the per-row markings the
        approver made (some approved, some rejected). Requires every row to be
        marked and every rejected row to carry a reason (issue 3)."""
        for rec in self:
            if rec.state != 'pending':
                raise UserError(_(
                    'This request has already been decided (%s).'
                ) % dict(rec._fields['state'].selection).get(rec.state))
            rec._check_may_decide()
            undecided = rec.line_ids.filtered(lambda l: not l.decision)
            if undecided:
                raise UserError(_(
                    'Mark every row Approve or Reject first — %(n)s row(s) '
                    'are still undecided. (Use Approve All / Reject All to '
                    'decide the whole request in one go.)'
                ) % {'n': len(undecided)})
            no_reason = rec.line_ids.filtered(
                lambda l: l.decision == 'rejected' and not l.reason)
            if no_reason:
                raise UserError(_(
                    'Every rejected row needs a Reason — %(n)s still missing '
                    'one.'
                ) % {'n': len(no_reason)})
            rec._commit_decisions()
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


class SignRequestWay4Tech(models.Model):
    """CR3-FINAL round 3, item 8 — signing in Sign approves the request.

    The contract shows status only; the decision is made by signing. When a
    sign.request completes, the linked approval is approved on behalf of
    whoever signed it, and the normal guards still apply (a signature from the
    requester is refused, keeping separation of duties intact even if someone
    routes a document to themselves).
    """
    _inherit = 'sign.request'

    def _way4tech_sync_approval(self):
        Approval = self.env['way4tech.manpower.approval.request']
        for sign_request in self:
            approval = Approval.sudo().search(
                [('sign_request_id', '=', sign_request.id)], limit=1)
            if not approval or approval.state != 'pending':
                continue
            signer = sign_request.request_item_ids.filtered(
                lambda i: i.state == 'completed' and i.partner_id
            )[:1]
            user = self.env['res.users'].sudo().search(
                [('partner_id', '=', signer.partner_id.id)], limit=1,
            ) if signer else self.env['res.users']
            if user and user == approval.requested_by:
                approval.message_post(body=_(
                    'Signature by the requester ignored — separation of '
                    'duties requires a different approver.'
                ))
                continue
            # A completed signature = Approve All (the signer authorises the
            # whole request). Marks every row approved, then commits (issue 3).
            approval.line_ids.write({'decision': 'approved', 'reason': False})
            approval.sudo().write({'approver_id': (user or approval.approver_ids[:1]).id})
            approval.sudo()._commit_decisions()
            approval.message_post(body=_(
                'Approved via Sign document %s.'
            ) % sign_request.reference or '')

    def write(self, vals):
        result = super().write(vals)
        if vals.get('state') in ('signed', 'completed', 'done'):
            self._way4tech_sync_approval()
        return result


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
            ('consumed', 'Created'),
        ],
        string='Approval', compute='_compute_approval_state',
        help='Approval status of THIS row. Each row is approved on its own; '
             'approving one never unlocks another.',
    )
    approval_reason = fields.Char(
        compute='_compute_approval_state',
        help='Rejection reason for this row, if any.',
    )
    # CR3-FINAL round 5, issue 5: ONE column carries everything. Shows the
    # state, and on rejection shows the reason inline, so there is no second
    # permanently-blank "Approval Note" column.
    approval_label = fields.Char(
        string='Approval', compute='_compute_approval_state',
        help='Approval status shown on the row: Awaiting Approval / Approved / '
             'Rejected (with reason) / Created.',
    )

    def _compute_approval_state(self):
        Line = self.env['way4tech.manpower.approval.request.line']
        labels = {'none': '', 'pending': 'Awaiting Approval',
                  'approved': 'Approved', 'consumed': 'Created'}
        for rec in self:
            # Newest approval line for this exact row, regardless of consumed
            # or the request's overall state.
            line = Line.search([
                ('res_model', '=', rec._name),
                ('res_id', '=', rec.id),
            ], order='id desc', limit=1)
            if not line or line.request_id.state == 'cancelled':
                rec.approval_state = 'none'
                rec.approval_reason = False
                rec.approval_label = ''
                continue
            if line.consumed:
                # CR3-FINAL round 5, issue 4: once the document is created the
                # row is Created, not back to Awaiting.
                state, reason = 'consumed', False
            else:
                # A single ROW is only ever pending/approved/rejected — never
                # 'partial' (that is a request-level state, and assigning it
                # here crashed in round 4). An undecided line is Pending.
                state = line.decision or 'pending'
                reason = line.reason or line.request_id.reason or False
            rec.approval_state = state
            rec.approval_reason = reason
            if state == 'rejected':
                rec.approval_label = _('Rejected: %s') % (reason or _('no reason given'))
            else:
                rec.approval_label = labels.get(state, '')

    @api.ondelete(at_uninstall=False)
    def _way4tech_clean_approval_lines(self):
        """CR3-FINAL round 3: deleting a row must not leave an approval item
        pointing at a record that no longer exists.

        That dangling reference is what produced "Record does not exist or has
        been deleted (way4tech.manpower.invoice.block(6,))" when the contract
        was being cleared. Removing the line here, and voiding a request that
        is left with nothing to approve, keeps the two sides consistent.
        """
        Line = self.env['way4tech.manpower.approval.request.line']
        lines = Line.sudo().search([
            ('res_model', '=', self._name), ('res_id', 'in', self.ids),
        ])
        requests = lines.mapped('request_id')
        lines.unlink()
        for request in requests:
            if not request.line_ids and request.state in ('pending', 'approved'):
                request.message_post(body=_(
                    'Voided — every item it covered has been deleted.'
                ))
                request.state = 'cancelled'

    @api.ondelete(at_uninstall=False)
    def _way4tech_block_delete_when_completed(self):
        """CR5 item 7: no line may be deleted while its contract is Completed.
        (A full contract delete cascades at the DB level and does not run this,
        so archiving a contract is unaffected.) Bypassable via context."""
        if self.env.context.get('way4tech_skip_lock_guard'):
            return
        for rec in self:
            contract = rec.contract_id if 'contract_id' in rec._fields else False
            if contract and contract.state == 'completed':
                raise UserError(_(
                    'The contract for this line is Completed and locked. Reset '
                    'it to Draft before deleting its lines.'
                ))

    @api.model
    def _way4tech_default_period_date(self):
        """CR4 item 3: default an accounting/period date from the parent
        contract's Start Date (its month), NOT today, so line entries land in
        the record's month and the date picker opens there. Read from the
        `default_contract_id` the notebook tab puts in context. Falls back to
        today when there is no contract in context (rare)."""
        cid = self.env.context.get('default_contract_id')
        if cid:
            contract = self.env['way4tech.manpower.contract'].browse(cid)
            if contract.exists() and contract.start_date:
                return contract.start_date
        return fields.Date.context_today(self)

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

    @api.model_create_multi
    def create(self, vals_list):
        """CR5 item 7: a Completed contract is frozen, so no new line may be
        added under it until it is reopened with Reset to Draft. Covers the
        inline tabs and the standalone Project Expenses screen alike.
        Bypassable via context for internal flows."""
        if not self.env.context.get('way4tech_skip_lock_guard'):
            Contract = self.env['way4tech.manpower.contract']
            default_cid = self.env.context.get('default_contract_id')
            for vals in vals_list:
                cid = vals.get('contract_id') or default_cid
                if cid and Contract.browse(cid).state == 'completed':
                    raise UserError(_(
                        'This contract is Completed and locked. Reset it to '
                        'Draft before adding lines.'
                    ))
        return super().create(vals_list)

    def write(self, vals):
        """Part A point 14: editing an approved row voids its approval.

        Also walks UP to the parent invoice block. An approval is raised
        against the block, but the figures that matter live on its child
        income lines — editing a line without this would leave the block's
        approval standing against amounts nobody signed off.
        """
        # CR5 item 7: a Completed contract freezes its lines on every write
        # path (including the standalone Project Expenses screen). Idempotent
        # (real user changes only) and bypassable, so ORM recomputes and the
        # invoice/bill amount sync-back (way4tech_skip_move_sync) pass through.
        if not (self.env.context.get('way4tech_skip_lock_guard')
                or self.env.context.get('way4tech_skip_move_sync')):
            for rec in self:
                contract = rec.contract_id if 'contract_id' in rec._fields else False
                if (contract and contract.state == 'completed'
                        and way4tech_first_real_change(rec, vals)):
                    raise UserError(_(
                        'The contract for this line is Completed and locked. '
                        'Reset it to Draft before changing its lines.'
                    ))
        result = super().write(vals)
        watched = {'amount', 'amount_total', 'quantity', 'price', 'hours',
                   'rate', 'budget_amount', 'description', 'line_ids'}
        if not (watched & set(vals)) or self.env.context.get(
                'way4tech_skip_approval_invalidation'):
            return result
        Request = self.env['way4tech.manpower.approval.request']
        Request._invalidate_for(self)
        if 'invoice_block_id' in self._fields:
            blocks = self.mapped('invoice_block_id')
            if blocks:
                Request._invalidate_for(blocks)
        # Item 4 (findings 3/6): mirror the invoice-block walk-up for bill
        # blocks — editing a block's expense line (description / account /
        # amount) must void the BLOCK's approval, exactly as on the income side.
        if 'bill_block_id' in self._fields:
            bill_blocks = self.mapped('bill_block_id')
            if bill_blocks:
                Request._invalidate_for(bill_blocks)
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
    # ── CR3-FINAL round 3, item 3: per-line decision ──────────────────────
    # One bad line used to force the whole request to be rejected and
    # everything resubmitted. The approver can now tick lines and apply
    # Approve or Reject to just that selection.
    decision = fields.Selection(
        selection=[('approved', 'Approved'), ('rejected', 'Rejected')],
        string='Decision', copy=False,
        help='Set individually by the approver. Blank means it follows the '
             "request's overall state.",
    )
    reason = fields.Char(
        string='Reason', copy=False,
        help='Required when this specific line is rejected.',
    )

    def action_approve_selected(self):
        """CR3-FINAL round 5, issue 3 — mark this row Approved (PROVISIONAL).

        This only sets the marking. It does NOT commit or close the request —
        the request stays Pending and fully decidable until the approver
        presses Approve All / Reject All / Partially Approve in the header.
        """
        for line in self:
            if line.request_id.state != 'pending':
                raise UserError(_(
                    'This request has already been decided — its markings are '
                    'locked.'
                ))
            line.request_id._check_may_decide()
            line.write({'decision': 'approved', 'reason': False})
        return True

    def action_reject_selected(self):
        """Mark this row Rejected (PROVISIONAL) — a Reason is required. Like
        Approve, this only marks; nothing commits until a header button."""
        for line in self:
            if line.request_id.state != 'pending':
                raise UserError(_(
                    'This request has already been decided — its markings are '
                    'locked.'
                ))
            line.request_id._check_may_decide()
            if not line.reason:
                raise UserError(_(
                    'Type a Reason on "%s" before marking it Rejected — the '
                    'requester needs to know what to correct.'
                ) % (line.description or line.id))
            line.decision = 'rejected'
        return True
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
