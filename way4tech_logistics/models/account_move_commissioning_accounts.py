# -*- coding: utf-8 -*-
"""Commissioning client invoices: apply the configured client-side accounts.

Payroll & Accounting Setup > Commissioning Business carries a Client
Receivable Account and a Client Output VAT Account (2026-09-15), the
counterpart of the Manpower "Billing" block. Commissioning client invoices are
plain customer invoices raised in the Commissioning sales journal (opened from
the record, or straight in Accounting), so the accounts are applied here, on
account.move, and nowhere else:

  * the receivable line is re-pointed when such an invoice is created and again
    right before it is confirmed (Odoo keeps a receivable account once set; it
    only recomputes it when the customer or journal is changed by hand);
  * the VAT lines are re-pointed right before the invoice is confirmed, the one
    moment Odoo no longer regenerates tax lines from the product lines.

Nothing happens for a move outside that journal, for a journal that is also the
Manpower sales journal (ambiguous, left to Odoo), when the settings row has no
value, or for a move that is no longer draft. With both fields empty every
invoice posts exactly as before.
"""
from odoo import api, fields, models


class AccountMoveCommissioningAccounts(models.Model):
    _inherit = 'account.move'

    # 2026-09-21: set when a client invoice is opened from a Commissioning
    # record (Invoices tab > Client Invoices). It only carries the record's
    # analytic distribution onto the invoice lines; matching for the
    # settlement picker is unchanged (partner + journal).
    way4tech_commission_receipt_id = fields.Many2one(
        'way4tech.commission.receipt', string='Commissioning Record',
        copy=False, index=True, ondelete='set null')

    def _way4tech_apply_commissioning_analytic(self):
        """Give every product line that has no analytic distribution the one
        configured on the Commissioning record the invoice was raised from.
        The record is the source of truth; a distribution typed on a line by
        hand is left alone. Mirrors what the subcontractor bill does."""
        for move in self:
            receipt = move.way4tech_commission_receipt_id
            if move.state != 'draft' or not receipt or not receipt.analytic_distribution:
                continue
            lines = move.invoice_line_ids.filtered(
                lambda l: l.display_type == 'product' and not l.analytic_distribution)
            if lines:
                lines.write({'analytic_distribution': receipt.analytic_distribution})

    def _way4tech_commissioning_client_settings(self):
        """The settings row whose Commissioning sales journal this move is in,
        or an empty recordset. Read-only: never creates a settings row."""
        self.ensure_one()
        Settings = self.env['way4tech.payroll.settings']
        if self.move_type not in ('out_invoice', 'out_refund') or not self.journal_id:
            return Settings
        settings = Settings.sudo().search(
            [('company_id', '=', self.company_id.id)], limit=1)
        if (not settings or not settings.commission_journal_id
                or settings.commission_journal_id != self.journal_id
                or settings.commission_journal_id == settings.manpower_journal_id):
            return Settings
        return settings

    def _way4tech_apply_commissioning_client_accounts(self, with_vat=True):
        for move in self:
            if move.state != 'draft':
                continue
            settings = move._way4tech_commissioning_client_settings()
            if not settings:
                continue
            receivable = settings.commissioning_receivable_account_id
            if receivable:
                term_lines = move.line_ids.filtered(
                    lambda l: l.display_type == 'payment_term'
                    and l.account_id != receivable)
                if term_lines:
                    term_lines.write({'account_id': receivable.id})
            vat = settings.commissioning_vat_output_account_id
            if with_vat and vat:
                tax_lines = move.line_ids.filtered(
                    lambda l: l.display_type == 'tax'
                    and l.tax_line_id.type_tax_use == 'sale'
                    and l.account_id != vat)
                if tax_lines:
                    tax_lines.write({'account_id': vat.id})

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        # Receivable only at this point: the tax lines are still being
        # regenerated from the product lines while the invoice is edited.
        moves._way4tech_apply_commissioning_client_accounts(with_vat=False)
        moves._way4tech_apply_commissioning_analytic()
        return moves

    def write(self, vals):
        res = super().write(vals)
        if 'invoice_line_ids' in vals or 'line_ids' in vals:
            # Lines added while the invoice is edited in the form.
            self._way4tech_apply_commissioning_analytic()
        return res

    def _post(self, soft=True):
        self._way4tech_apply_commissioning_client_accounts(with_vat=True)
        self._way4tech_apply_commissioning_analytic()
        return super()._post(soft=soft)
