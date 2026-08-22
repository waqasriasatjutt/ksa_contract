# -*- coding: utf-8 -*-
"""CR2 G4 (19.0.2.8.0) — Two-way sync + delete propagation between
account.move and the four Manpower Contract source-line models.

Before G4, sync was one-directional (line → move) and one-shot at
creation. When the accountant edited amount_untaxed on the customer
invoice / vendor bill in the default Accounting UI, the Billing Summary
refreshed (via depends on invoice_ids.amount_untaxed) but the contract
TAB line's amount stayed frozen at its create-time snapshot. Deleting
the move left the tab line's FK dangling with state stuck at
invoiced/billed (no ondelete on the Many2one).

This module closes both gaps with two hooks on account.move — a single
place to reason about the cross-model invariant.

Skeptic amendments applied (all pre-review issues fixed here):
- (A) Sync reads *line.price_subtotal* via a per-source `invoice_line_id`
  / `bill_line_id` FK on each source-line model — NOT `move.amount_untaxed`.
  This prevents multi-invoice-line data corruption (adding a discount
  row would have set source-line price to the whole invoice total).
- (C) `_relevant` trigger set omits 'state' and gates on a real
  amount_untaxed diff (batch-posting 200 invoices no longer fans out
  800 no-op writes).
- (D) Unified context key `way4tech_skip_move_sync` used in BOTH the
  override guard and the adapters — no fragile mismatch.
- (G) Search scoped by move_type per line model — bill-linked models
  ignore customer invoices and vice-versa.

Recursion guard
---------------
Both hooks respect `self.env.context.get('way4tech_skip_move_sync')`.
Adapter writes on line models set this flag so we do NOT re-enter our
own write() override.
"""
import logging

from odoo import models, api, _

_logger = logging.getLogger(__name__)

_SYNC_SKIP_KEY = 'way4tech_skip_move_sync'

# Per-source-line-model mapping used by ALL hooks. Order is stable for
# grep-ability. Each tuple: (model_name, move_fk_field, draft_state,
# done_state, allowed_move_types). Amendment G — scope search per model, no
# wasted probes across in vs out invoices.
#
# CR3-FINAL round 2, bug 4: the invoice BLOCK is in this map too, and every
# entry now carries its done_state so the source row can follow the document
# both ways (see _way4tech_sync_source_states).
_SOURCE_LINE_MAP = (
    ('way4tech.manpower.invoice.block',        'invoice_id', 'draft', 'invoiced', ('out_invoice', 'out_refund')),
    ('way4tech.manpower.contract.income.line', 'invoice_id', 'draft', 'invoiced', ('out_invoice', 'out_refund')),
    ('way4tech.manpower.timesheet',            'invoice_id', 'draft', 'invoiced', ('out_invoice', 'out_refund')),
    ('way4tech.manpower.project.expense',      'bill_id',    'draft', 'billed',   ('in_invoice', 'in_refund')),
    ('way4tech.manpower.commission.line',      'bill_id',    'draft', 'billed',   ('in_invoice', 'in_refund')),
    # CB1 item 7: a Commissioning subcontractor bill that is deleted or
    # cancelled must revert its settlement to draft and clear the FK, exactly
    # like the Manpower lines above. The settlement has no _sync_amount_from_move
    # so only the STATE sync applies (it drives the bill amount, not vice versa).
    ('way4tech.commission.settlement',         'bill_id',    'draft', 'billed',   ('in_invoice', 'in_refund')),
    # Item 4: a Bill Block's combined vendor bill drives the block state exactly
    # like the invoice block — posted → billed, reset-to-draft → 'Bill Draft'
    # (the block carries that middle state), cancel/delete → released to draft.
    # The block's own expense line_ids are the project.expense rows above, so
    # they flip together with the block on the same move event.
    ('way4tech.manpower.bill.block',           'bill_id',    'draft', 'billed',   ('in_invoice', 'in_refund')),
    # Part 1 (2026-08): Other Payable line/block link to a JOURNAL ENTRY (an
    # 'entry' move). Deleting that entry resets the row to draft + clears the FK
    # (and, via the unlink override, orphans its approval) exactly like a bill.
    ('way4tech.manpower.other.payable',        'move_id',    'draft', 'posted',   ('entry',)),
    ('way4tech.manpower.other.payable.block',  'move_id',    'draft', 'posted',   ('entry',)),
)


class AccountMoveWay4TechSync(models.Model):
    _inherit = 'account.move'

    # ── CR3-FINAL round 2, bug 4: source row follows the document state ────
    def _way4tech_sync_source_states(self):
        """Push this move's state back onto the contract rows that made it.

        Before this, a row was flipped to Invoiced/Billed at CREATE time and
        stayed there forever. Resetting the invoice to draft in Accounting
        left the Project Income block still badged "Invoiced" with a View
        Invoice button, while the Billing Summary had already dropped to 0 —
        the two halves of the screen disagreed.

        Mapping: posted → done_state; draft or cancelled → draft_state, so
        the row becomes actionable again and its button reverts.
        """
        for move in self:
            if move.move_type not in ('out_invoice', 'out_refund',
                                      'in_invoice', 'in_refund'):
                continue
            for model_name, fk_field, draft_state, done_state, allowed in _SOURCE_LINE_MAP:
                if move.move_type not in allowed:
                    continue
                rows = self.env[model_name].sudo().search([(fk_field, '=', move.id)])
                if not rows:
                    continue
                # CR3-FINAL round 2, new item 1 — three outcomes, not two:
                #   posted    → done  (Invoiced / Bill Created)
                #   draft     → still LINKED. The row must keep offering View,
                #               never a Create button that can only raise
                #               "already produced invoice X". Blocks have a
                #               dedicated 'invoice_draft' state for this; the
                #               simpler line models just hold their done state.
                #   cancelled → RELEASED: clear the FK and drop to draft, so a
                #               fresh document can be created.
                if move.state == 'posted':
                    vals = {'state': done_state}
                elif move.state == 'cancel':
                    vals = {'state': draft_state, fk_field: False}
                else:  # draft — keep the link
                    has_mid = 'invoice_draft' in dict(
                        rows._fields['state'].selection,
                    )
                    vals = {'state': 'invoice_draft' if has_mid else done_state}
                stale = rows.filtered(
                    lambda r: any(r[k] != v for k, v in vals.items())
                )
                if stale:
                    stale.with_context(**{_SYNC_SKIP_KEY: True}).write(vals)

    # CR3-FINAL round 5: the manual budget-actual "dirty" trigger is GONE.
    # budget.line.actual_amount now derives from the contract's Project Expense
    # lines with a real @api.depends, so posting/cancelling a bill flows to it
    # through the ORM dependency graph — no hand-rolled recompute needed.
    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        posted._way4tech_sync_source_states()
        return posted

    def button_draft(self):
        result = super().button_draft()
        self._way4tech_sync_source_states()
        return result

    def button_cancel(self):
        result = super().button_cancel()
        self._way4tech_sync_source_states()
        return result

    # ── Two-way sync (item 3) ──────────────────────────────────────────────
    def write(self, vals):
        # Amendment C: capture old amount_untaxed so we only fan out when
        # it actually shifts. Cheap dict; only kept when relevant fields
        # are being written.
        _relevant = {'invoice_line_ids', 'line_ids', 'amount_untaxed', 'amount_total'}
        do_check_diff = bool(_relevant & set(vals.keys())) and not self.env.context.get(_SYNC_SKIP_KEY)
        old_amounts = {m.id: m.amount_untaxed for m in self} if do_check_diff else {}

        result = super().write(vals)

        if not do_check_diff:
            return result
        for move in self:
            # Amendment G: only fan out for the move_types that could
            # actually be linked to a source line.
            if move.move_type not in ('out_invoice', 'out_refund', 'in_invoice', 'in_refund'):
                continue
            # Amendment C: skip when amount_untaxed did not actually move.
            if old_amounts.get(move.id) == move.amount_untaxed:
                continue
            for model_name, fk_field, _draft, _done, allowed_types in _SOURCE_LINE_MAP:
                if move.move_type not in allowed_types:
                    continue
                lines = self.env[model_name].sudo().search([(fk_field, '=', move.id)])
                for line in lines:
                    if hasattr(line, '_sync_amount_from_move'):
                        line._sync_amount_from_move(move)
        return result

    # ── Delete propagation (item 4 companion) ──────────────────────────────
    def unlink(self):
        if not self.env.context.get(_SYNC_SKIP_KEY):
            for move in self:
                if not move.exists():
                    continue
                for model_name, fk_field, draft_state, _done, allowed_types in _SOURCE_LINE_MAP:
                    if move.move_type not in allowed_types:
                        continue
                    lines = self.env[model_name].sudo().search([(fk_field, '=', move.id)])
                    if lines:
                        lines.with_context(**{_SYNC_SKIP_KEY: True}).write({
                            fk_field: False,
                            'state': draft_state,
                        })
                        # Part 2 Orphaned (2026-08): the document these rows were
                        # approved for has just been deleted, so void their
                        # approval FOR AUDIT — per line, so any sibling items on
                        # the same request stay valid. The rows are back to draft
                        # and can be freshly re-approved (an orphaned line is
                        # ignored by the gate, so it never blocks a new request).
                        appr = self.env['way4tech.manpower.approval.request.line'].sudo().search([
                            ('res_model', '=', model_name),
                            ('res_id', 'in', lines.ids),
                            ('orphaned', '=', False),
                        ])
                        if appr:
                            appr.write({'orphaned': True})
                            for al in appr:
                                al.request_id.message_post(
                                    body='Item "%s" orphaned — its invoice/bill '
                                         'was deleted.' % (al.description or al.res_id))
                # Detach from contract.invoice_ids M2M so smart-button counts
                # and Billing Summary recompute drop the deleted move.
                if move.move_type in ('out_invoice', 'out_refund'):
                    contracts = self.env['way4tech.manpower.contract'].sudo().search([
                        ('invoice_ids', 'in', move.id),
                    ])
                    for contract in contracts:
                        contract.with_context(**{_SYNC_SKIP_KEY: True}).write({
                            'invoice_ids': [(3, move.id)],
                        })
        return super().unlink()
