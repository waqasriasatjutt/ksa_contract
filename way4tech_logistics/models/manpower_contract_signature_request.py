# -*- coding: utf-8 -*-
"""CR2 G5 (19.0.2.9.0) — Monthly signature-request workflow for Manpower
Contracts. One request per (contract, month); Create/Confirm actions on
the 6 line-tabs are gated behind state='approved' for the line's month.

Simplification (skeptic amendment 4): the snapshot_json is a pure audit
trail — approval unlocks Create-Invoice/Create-Bill for that month but
does NOT restore the snapshot into live data. The whole-contract view-
lockout was dropped after the skeptic pointed out it would freeze every
tab even when the pending approval is for an unrelated month; the real
enforcement is the per-month gate at create-time (_require_month_approval
on the contract) plus the chatter/audit trail on the request itself.

Race-safe: uniqueness of active (contract, month) is enforced by a
partial unique index at the DB level (skeptic amendment 3), not just
@api.constrains — two accountants clicking Send for Signature at the
same instant can't split-brain the gate.
"""
import json

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class Way4TechManpowerContractSignatureRequest(models.Model):
    _name = 'way4tech.manpower.contract.signature.request'
    _description = 'Manpower Contract — Monthly Signature Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='Reference', compute='_compute_name', store=True,
    )
    contract_id = fields.Many2one(
        'way4tech.manpower.contract', string='Contract',
        required=True, ondelete='cascade', tracking=True,
    )
    company_id = fields.Many2one(
        related='contract_id.company_id', store=True, readonly=True,
    )
    currency_id = fields.Many2one(
        related='contract_id.currency_id', store=True, readonly=True,
    )
    month = fields.Char(
        string='Month (MM/YYYY)', required=True, tracking=True,
        help='Two-digit-month / four-digit-year bucket this request covers. '
             'Create-Invoice / Create-Bill actions on the contract only run '
             "for lines dated in this month once state='approved'.",
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('pending', 'Pending Signature'),
            ('approved', 'Approved'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status', default='draft', tracking=True, copy=False,
    )
    snapshot_json = fields.Text(
        string='Snapshot (JSON)', readonly=True, copy=False,
        help='Serialised dict of the 6 tabs at submit time. Audit trail '
             "only — approval doesn't restore this into the live tabs.",
    )
    signed_by = fields.Many2one(
        'res.users', string='Signed By', readonly=True, copy=False, tracking=True,
    )
    signed_date = fields.Datetime(
        string='Signed On', readonly=True, copy=False, tracking=True,
    )
    notes = fields.Text(string='Notes')

    @api.depends('contract_id.name', 'month')
    def _compute_name(self):
        for rec in self:
            rec.name = '%s — %s' % (rec.contract_id.name or '', rec.month or '')

    @api.constrains('contract_id', 'month', 'state')
    def _check_unique_active(self):
        """Friendly UserError guard. Real enforcement is the partial unique
        index created in init() below (skeptic amendment 3)."""
        for rec in self:
            if rec.state == 'cancelled':
                continue
            dup = self.search([
                ('id', '!=', rec.id),
                ('contract_id', '=', rec.contract_id.id),
                ('month', '=', rec.month),
                ('state', '!=', 'cancelled'),
            ], limit=1)
            if dup:
                raise ValidationError(_(
                    'Another active signature request already exists for '
                    'contract "%s" in month %s. Cancel it before creating '
                    'a new one.'
                ) % (rec.contract_id.name or '', rec.month or ''))

    def init(self):
        """Create a partial unique index enforcing one active request per
        (contract, month) at the DB layer. @api.constrains is python-only
        and racy under concurrent transactions; this index is the real
        guard (skeptic amendment 3). Raw SQL used deliberately — Odoo 19's
        ``sql.create_index()`` signature (columns positional list, then
        method/where/unique kwargs) previously misinterpreted the WHERE
        clause as the USING method and produced a syntax error."""
        self.env.cr.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS way4tech_signature_req_uniq_active "
            "ON %s (contract_id, month) WHERE state <> 'cancelled'" % self._table
        )

    # ── State transitions ──────────────────────────────────────────────────
    def action_confirm_pending(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_(
                    'Only Draft signature requests can be submitted for signature.'
                ))
            rec._capture_snapshot()
            rec.state = 'pending'
        return True

    def action_approve(self):
        for rec in self:
            if rec.state != 'pending':
                raise UserError(_(
                    'Only Pending signature requests can be approved.'
                ))
            rec.write({
                'state': 'approved',
                'signed_by': self.env.user.id,
                'signed_date': fields.Datetime.now(),
            })
        return True

    def action_cancel(self):
        for rec in self:
            if rec.state == 'approved':
                raise UserError(_(
                    'Cannot cancel an approved signature request — reset '
                    'the linked invoices/bills first.'
                ))
            rec.state = 'cancelled'
        return True

    def action_reset_draft(self):
        for rec in self:
            if rec.state != 'cancelled':
                raise UserError(_(
                    'Only Cancelled signature requests can be reset to Draft.'
                ))
            rec.state = 'draft'
        return True

    # ── Snapshot capture ──────────────────────────────────────────────────
    def _capture_snapshot(self):
        """Serialise all 6 tabs of the parent contract into snapshot_json.
        Called at draft→pending. Pure audit trail."""
        self.ensure_one()
        c = self.contract_id
        payload = {
            'contract': {
                'name': c.name, 'reference': c.reference or '',
                'client': c.client_id.name or '', 'month': self.month,
            },
            'income': [{
                'date': str(l.accounting_date or ''),
                'invoice_date': str(l.invoice_date or ''),
                'description': l.description or '',
                'account': l.sale_account_id.display_name or '',
                'qty': l.quantity, 'price': l.price, 'amount': l.amount,
            } for l in c.income_line_ids],
            'direct_cost': [{
                'date': str(l.date or ''), 'type': l.category_id.name or '',
                'vendor': l.vendor_id.name or '', 'amount': l.amount,
            } for l in c.direct_cost_line_ids],
            'operating_exp': [{
                'date': str(l.date or ''), 'type': l.category_id.name or '',
                'vendor': l.vendor_id.name or '', 'amount': l.amount,
            } for l in c.operating_exp_line_ids],
            'timesheets': [{
                'date': str(l.date or l.start_date or ''),
                'employee': l.employee_id.name or '',
                'hours': l.hours, 'rate': l.rate, 'amount': l.amount,
            } for l in c.timesheet_ids],
            'budget': [{
                'type': l.category_id.name or '',
                'budget': l.budget_amount, 'actual': l.actual_amount,
                'remaining': l.remaining, 'state': l.state,
            } for l in c.budget_line_ids],
            'commission': [{
                'employee': l.employee_id.name or '',
                'amount': l.amount,
            } for l in c.commission_line_ids],
        }
        self.snapshot_json = json.dumps(payload, default=str)
