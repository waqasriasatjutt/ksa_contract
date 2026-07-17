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

# Per-source-line-model mapping used by BOTH hooks. Order is stable for
# grep-ability. Each tuple: (model_name, move_fk_field, draft_state,
# allowed_move_types). Amendment G — scope search per model, no wasted
# probes across in vs out invoices.
_SOURCE_LINE_MAP = (
    ('way4tech.manpower.contract.income.line', 'invoice_id', 'draft', ('out_invoice', 'out_refund')),
    ('way4tech.manpower.timesheet',            'invoice_id', 'draft', ('out_invoice', 'out_refund')),
    ('way4tech.manpower.project.expense',      'bill_id',    'draft', ('in_invoice', 'in_refund')),
    ('way4tech.manpower.commission.line',      'bill_id',    'draft', ('in_invoice', 'in_refund')),
)


class AccountMoveWay4TechSync(models.Model):
    _inherit = 'account.move'

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
            for model_name, fk_field, _draft, allowed_types in _SOURCE_LINE_MAP:
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
                for model_name, fk_field, draft_state, allowed_types in _SOURCE_LINE_MAP:
                    if move.move_type not in allowed_types:
                        continue
                    lines = self.env[model_name].sudo().search([(fk_field, '=', move.id)])
                    if lines:
                        lines.with_context(**{_SYNC_SKIP_KEY: True}).write({
                            fk_field: False,
                            'state': draft_state,
                        })
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
