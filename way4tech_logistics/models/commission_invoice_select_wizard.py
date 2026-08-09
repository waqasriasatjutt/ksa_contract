# -*- coding: utf-8 -*-
"""CB1 (19.0.4.0.0) §5 — Client-invoice selection wizard.

A custom wizard (not a plain many2many) so each candidate invoice shows its
Total / Received / Pending / Project before it is picked. Lists the selected
client's Commissioning invoices that are not yet fully consumed, with live
Received/Pending computed from this module's own allocations (display only,
nothing posted). On confirm it writes the allocation rows on the settlement and
seeds Full Receipt Amount; the actual per-invoice split is FIFO (oldest first).
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CommissionInvoiceSelectWizard(models.TransientModel):
    _name = 'way4tech.commission.invoice.select.wizard'
    _description = 'Select Client Invoices for a Commissioning Settlement'

    settlement_id = fields.Many2one(
        'way4tech.commission.settlement', required=True)
    partner_id = fields.Many2one(
        related='settlement_id.partner_id', string='Client')
    currency_id = fields.Many2one(related='settlement_id.currency_id')
    line_ids = fields.One2many(
        'way4tech.commission.invoice.select.line', 'wizard_id',
        string='Invoices')
    selected_count = fields.Integer(compute='_compute_totals')
    selected_total = fields.Monetary(
        compute='_compute_totals', currency_field='currency_id')
    selected_pending = fields.Monetary(
        compute='_compute_totals', currency_field='currency_id')

    @api.depends('line_ids.selected', 'line_ids.pending', 'line_ids.invoice_total')
    def _compute_totals(self):
        for w in self:
            sel = w.line_ids.filtered('selected')
            w.selected_count = len(sel)
            w.selected_total = sum(sel.mapped('invoice_total'))
            w.selected_pending = sum(sel.mapped('pending'))

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        settlement_id = self.env.context.get('default_settlement_id')
        if settlement_id:
            settlement = self.env['way4tech.commission.settlement'].browse(settlement_id)
            res['settlement_id'] = settlement_id
            res['line_ids'] = [(0, 0, v) for v in self._build_lines(settlement)]
        return res

    def _build_lines(self, settlement):
        client = settlement.partner_id
        settings = settlement.receipt_id._settings()
        Alloc = self.env['way4tech.commission.settlement.invoice']
        domain = [('partner_id', '=', client.id), ('move_type', '=', 'out_invoice'),
                  ('state', '=', 'posted'), ('company_id', '=', settlement.company_id.id)]
        # Scope to the Commissioning sales journal only (never Direct Business).
        if settings.commission_journal_id:
            domain.append(('journal_id', '=', settings.commission_journal_id.id))
        out = []
        for inv in self.env['account.move'].search(domain, order='invoice_date, id'):
            received = Alloc._received_for_invoice(inv, exclude_settlement=settlement)
            pending = inv.amount_total - received
            if pending <= 0:
                continue
            already = settlement.allocation_ids.filtered(lambda a: a.invoice_id == inv)
            out.append({
                'invoice_id': inv.id, 'received': received, 'pending': pending,
                'selected': bool(already),
            })
        return out

    def action_confirm(self):
        self.ensure_one()
        settlement = self.settlement_id
        # Guard on invoice_id too: a stripped/empty row must never be treated as
        # a selection, and pending is recomputed server-side (never trusted from
        # the possibly-stripped display field).
        selected = self.line_ids.filtered(lambda l: l.selected and l.invoice_id)
        if not selected:
            raise UserError(_('Select at least one invoice.'))
        Alloc = self.env['way4tech.commission.settlement.invoice']
        settlement.allocation_ids.unlink()
        total_pending = 0.0
        vals = []
        for ln in selected.sorted(lambda l: (l.invoice_id.invoice_date or fields.Date.today(),
                                             l.invoice_id.id)):
            inv = ln.invoice_id
            received = Alloc._received_for_invoice(inv, exclude_settlement=settlement)
            pending = (inv.amount_total or 0.0) - received
            total_pending += max(pending, 0.0)
            vals.append((0, 0, {'invoice_id': inv.id, 'allocated_amount': 0.0}))
        settlement.write({
            'allocation_ids': vals,
            'full_receipt_amount': total_pending,
        })
        settlement._reallocate_fifo()
        # Reopen the settlement fresh from the database so the newly linked
        # invoices and the seeded Full Receipt Amount appear immediately. The
        # wizard wrote via ORM, so the form underneath would otherwise show a
        # stale datapoint until a manual page refresh. Display/navigation only —
        # no change to the selection, linking or allocation logic above.
        return {
            'type': 'ir.actions.act_window',
            'name': _('Settlement'),
            'res_model': 'way4tech.commission.settlement',
            'res_id': settlement.id,
            'view_mode': 'form',
            'view_id': self.env.ref('way4tech_logistics.view_commission_settlement_form').id,
            'target': 'current',
        }


class CommissionInvoiceSelectLine(models.TransientModel):
    _name = 'way4tech.commission.invoice.select.line'
    _description = 'Commissioning Invoice Selection Line'
    _order = 'invoice_date, id'

    wizard_id = fields.Many2one(
        'way4tech.commission.invoice.select.wizard', required=True,
        ondelete='cascade')
    # NOT required at the DB level: the OWL client strips readonly x2many values
    # on save, so a required invoice_id would raise "Missing required value" the
    # moment the wizard is confirmed. It is kept writable in the view (so it
    # round-trips) and validated in action_confirm instead.
    invoice_id = fields.Many2one('account.move', string='Invoice')
    invoice_date = fields.Date(related='invoice_id.invoice_date', string='Date')
    invoice_total = fields.Monetary(
        related='invoice_id.amount_total', string='Total (incl VAT)',
        currency_field='currency_id')
    received = fields.Monetary(string='Received', currency_field='currency_id')
    pending = fields.Monetary(string='Pending', currency_field='currency_id')
    project = fields.Char(compute='_compute_project', string='Project')
    selected = fields.Boolean(string='Select')
    currency_id = fields.Many2one(related='invoice_id.company_id.currency_id')

    @api.depends('invoice_id')
    def _compute_project(self):
        for ln in self:
            proj = ln.invoice_id.way4tech_project_id if 'way4tech_project_id' in ln.invoice_id._fields else False
            ln.project = proj.name if proj else ''
