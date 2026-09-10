# -*- coding: utf-8 -*-
"""CB1 (19.0.4.0.0) — Commissioning Business record (project header).

Business model: AlZain Towers holds the CR + VAT registration. A subcontractor
with no company of his own uses AlZain's documents to bill his clients. AlZain
issues the client invoice in its own name; for lending the documents it keeps
5% of the ex-VAT amount and the subcontractor gets 95%. VAT is AlZain's and is
remitted to ZATCA, never shared.

This model is the PROJECT record: one subcontractor + one client pair. It stays
open from start to end; work is recorded over time as SETTLEMENT lines
(``way4tech.commission.settlement``), each one a receipt with its own date.
ALL amounts, reporting and period grouping derive from the settlement line's
own date — the header carries no period of its own.

Standard accrual accounting only. No holding accounts, no deferral. The client
invoice already posts the full ex-VAT to Commissioning Biz Sale (410002); the
subcontractor bill posts the 95% to 520002 / 210002; the 5% gross profit is the
residual margin. No separate commission invoice is raised (that would double
count 410002).

Evolved in place from the old simple commission-receipt model (CB1 §-decision).
Old per-receipt amount fields (vat_amount, total_invoice_amount and the
commission-invoice flow) are removed — the calculation bug they carried is
gone. The 2 pre-existing test records are disposable; no migration.
"""
from datetime import date, timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CommissionReceipt(models.Model):
    _name = 'way4tech.commission.receipt'
    _description = 'Commissioning Business Record'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'analytic.mixin']
    _order = 'start_date desc, reference desc, id desc'
    _rec_name = 'name'

    # ── Identity ──────────────────────────────────────────────────────────
    name = fields.Char(
        string='Name', copy=False, tracking=True,
        help='Auto-generated as "Subcontractor - Client - Start Month" when '
             'left blank. Editable; a name you type is kept.')
    name_is_auto = fields.Boolean(
        string='Name Auto-Generated', default=False, copy=False, readonly=True)
    reference = fields.Char(
        string='Reference', readonly=True, copy=False, index=True,
        help='SUB/YYYY/MM/NNNN — month from the Start Date, counter resetting '
             'each month. Minted by a Python counter, not an ir.sequence '
             'date-range (which had the yearly-bucket defect on the Manpower '
             'PRO series).')

    # ── Parties ───────────────────────────────────────────────────────────
    partner_id = fields.Many2one(
        'res.partner', string='Client', required=True, tracking=True,
        help='The client AlZain invoices (in its own name) on the '
             "subcontractor's behalf.")
    subcontractor_id = fields.Many2one(
        'res.partner', string='Subcontractor', required=True,
        domain=[('supplier_rank', '>', 0)], tracking=True,
        help='The subcontractor doing the work, who gets 95% of the ex-VAT.')
    client_po_id = fields.Many2one(
        'way4tech.client.po', string='Client PO',
        help='Optional link to the client PO this work is against.')
    salesperson_id = fields.Many2one(
        'hr.employee', string='Salesperson', tracking=True,
        help='Optional referrer. If none, no salesperson commission. '
             'Freelancers are entered as employees too (with a linked '
             'partner so the commission bill has a payee).')

    # ── Commission basis (default; each settlement can override) ──────────
    commission_is_fix = fields.Boolean(
        string='Fix Commission',
        help='Default basis copied onto new settlements: On = a fix amount, '
             'Off = a percent of the ex-VAT receipt.')
    commission_percent = fields.Float(
        string='Commission %', digits=(5, 2), default=5.0)
    commission_fix = fields.Monetary(
        string='Fix Commission Amount', currency_field='currency_id')

    # ── Reference / period ────────────────────────────────────────────────
    start_date = fields.Date(
        string='Start Date', required=True, default=fields.Date.context_today,
        tracking=True, index=True,
        help="Start of this record. Drives the auto-name and the SUB "
             "reference month only. Period reporting uses the settlement "
             "line date, never this.")
    end_date = fields.Date(
        string='End Date', tracking=True,
        help='Set when work with this client ends. The record stays open '
             'until then.')
    period = fields.Char(string='Period / Reference')
    way4tech_project_id = fields.Many2one('way4tech.project', string='Project')
    way4tech_category_id = fields.Many2one(
        'way4tech.entry.category', string='Entry Category')
    tag_ids = fields.Many2many(
        'way4tech.tag', 'way4tech_commissioning_tag_rel',
        'receipt_id', 'tag_id', string='Contract Tags')
    # analytic_distribution comes from analytic.mixin (allows >2 accounts).

    # ── Settlements ───────────────────────────────────────────────────────
    settlement_ids = fields.One2many(
        'way4tech.commission.settlement', 'receipt_id', string='Settlements')
    settlement_count = fields.Integer(
        compute='_compute_rollups', string='Settlements')
    # C5 (2026-08): these rollups are stored so they can serve as Pivot/Graph
    # MEASURES (aggregation needs a real column). store=True only; the compute
    # and its @api.depends are unchanged, so displayed values are identical.
    total_receipt = fields.Monetary(
        compute='_compute_rollups', store=True, currency_field='currency_id',
        string='Total Received (incl. VAT)')
    total_commission = fields.Monetary(
        compute='_compute_rollups', store=True, currency_field='currency_id',
        string='Total Commission (Gross Profit)')
    total_gross_payable = fields.Monetary(
        compute='_compute_rollups', store=True, currency_field='currency_id',
        string='Total Subcontractor Payable')
    total_vat = fields.Monetary(
        compute='_compute_rollups', store=True, currency_field='currency_id',
        string='Total VAT',
        help='VAT across all settlements = Total Received (incl. VAT) minus the '
             'ex-VAT total. Uses the VAT already implied on each settlement '
             'line; no separate VAT calculation.')
    bill_count = fields.Integer(compute='_compute_rollups', string='Bills')

    state = fields.Selection(
        selection=[('draft', 'Draft'), ('open', 'Open'), ('closed', 'Closed')],
        string='Status', default='draft', tracking=True, copy=False)

    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        related='company_id.currency_id', string='Currency',
        readonly=True, store=True)
    notes = fields.Text(string='Notes')

    # ── Rollups ───────────────────────────────────────────────────────────
    @api.depends('settlement_ids.full_receipt_amount',
                 'settlement_ids.commission_amount',
                 'settlement_ids.gross_payable',
                 'settlement_ids.receipt_excl_vat',
                 'settlement_ids.bill_id')
    def _compute_rollups(self):
        for rec in self:
            s = rec.settlement_ids
            rec.settlement_count = len(s)
            rec.total_receipt = sum(s.mapped('full_receipt_amount'))
            rec.total_commission = sum(s.mapped('commission_amount'))
            rec.total_gross_payable = sum(s.mapped('gross_payable'))
            # incl-VAT total minus ex-VAT total = the VAT already implied per line.
            rec.total_vat = rec.total_receipt - sum(s.mapped('receipt_excl_vat'))
            rec.bill_count = len(s.mapped('bill_id'))

    # ── Auto-name + SUB reference ─────────────────────────────────────────
    @api.model
    def _next_sub_reference(self, start_dt):
        """SUB/YYYY/MM/NNNN for start_dt's month — counter resets monthly.
        Same self-contained minter as the Manpower PRO series (never the
        yearly-range ir.sequence that resolved the month to 01)."""
        if not start_dt:
            start_dt = date.today()
        prefix = 'SUB/%s/%s/' % (start_dt.strftime('%Y'), start_dt.strftime('%m'))
        highest = 0
        for other in self.with_context(active_test=False).search(
                [('reference', '=like', prefix + '%')]):
            tail = (other.reference or '').rsplit('/', 1)[-1]
            if tail.isdigit():
                highest = max(highest, int(tail))
        return '%s%04d' % (prefix, highest + 1)

    def _build_auto_name(self, subcontractor, client, start_dt):
        sub = subcontractor.name or ''
        cli = client.name or ''
        mon = start_dt.strftime('%m/%Y') if start_dt else ''
        return '%s - %s - %s' % (sub, cli, mon)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            sd = fields.Date.to_date(vals.get('start_date')) or date.today()
            if not vals.get('reference'):
                vals['reference'] = self._next_sub_reference(sd)
            if not vals.get('name') and vals.get('subcontractor_id') and vals.get('partner_id'):
                sub = self.env['res.partner'].browse(vals['subcontractor_id'])
                cli = self.env['res.partner'].browse(vals['partner_id'])
                vals['name'] = self._build_auto_name(sub, cli, sd)
                vals['name_is_auto'] = True
        records = super().create(vals_list)
        # AR archived-account fallback: as soon as a Commissioning record binds a
        # client, make sure that client's receivable is active, so ANY customer
        # invoice later raised for them (here or straight in Accounting) posts to
        # a real account. No-op when the receivable is already active.
        for rec in records:
            if rec.partner_id:
                rec.partner_id._way4tech_ensure_active_receivable(rec.company_id)
        return records

    def write(self, vals):
        res = super().write(vals)
        # Keep an auto name in step when the driving fields change.
        drivers = {'subcontractor_id', 'partner_id', 'start_date'}
        if drivers & set(vals.keys()):
            for rec in self.filtered('name_is_auto'):
                rec.with_context(_skip_name_auto=True).name = rec._build_auto_name(
                    rec.subcontractor_id, rec.partner_id, rec.start_date)
        # AR archived-account fallback when the client is set / changed.
        if 'partner_id' in vals:
            for rec in self:
                if rec.partner_id:
                    rec.partner_id._way4tech_ensure_active_receivable(rec.company_id)
        return res

    # ── State + smart buttons ─────────────────────────────────────────────
    def action_open(self):
        self.write({'state': 'open'})

    def action_close(self):
        for rec in self:
            if not rec.end_date:
                rec.end_date = fields.Date.context_today(rec)
        self.write({'state': 'closed'})

    def action_reset_draft(self):
        self.write({'state': 'draft'})

    def action_view_bills(self):
        self.ensure_one()
        bills = self.settlement_ids.mapped('bill_id')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Subcontractor Bills'),
            'res_model': 'account.move',
            'domain': [('id', 'in', bills.ids)],
            'view_mode': 'list,form',
        }

    def action_view_client_invoices(self):
        """C6 (2026-08): open THIS client's Commissioning invoices using the
        NATIVE customer-invoice views. No invoicing logic is created or
        duplicated here — it hands straight to core Accounting's out_invoice
        form/list, pre-filtered to this client and pre-defaulted to the
        Commissioning sales journal. An invoice created here is therefore a
        completely standard account.move (identical accounting) and is
        immediately selectable by the existing Select Invoices wizard, which
        scopes to that same journal. Safe + additive: it never touches or
        parallels the wizard or core invoice creation."""
        self.ensure_one()
        # AR archived-account fallback (mirror of the payable fix): make sure
        # this client's receivable is active BEFORE the native invoice form is
        # opened, so the invoice they create posts to a real account instead of
        # failing on an archived default receivable.
        self.partner_id._way4tech_ensure_active_receivable(self.company_id)
        settings = self._settings()
        journal = settings.commission_journal_id
        domain = [('partner_id', '=', self.partner_id.id),
                  ('move_type', '=', 'out_invoice')]
        ctx = {
            'default_move_type': 'out_invoice',
            'default_partner_id': self.partner_id.id,
            'default_company_id': self.company_id.id,
        }
        if journal:
            domain.append(('journal_id', '=', journal.id))
            ctx['default_journal_id'] = journal.id
        return {
            'type': 'ir.actions.act_window',
            'name': _('Client Invoices'),
            'res_model': 'account.move',
            'domain': domain,
            'view_mode': 'list,form',
            'context': ctx,
        }

    # ── Fixes6 item 5 (2026-09): protect a processed record from deletion ──
    @api.ondelete(at_uninstall=False)
    def _unlink_protect_processed(self):
        """A Commissioning record can only be deleted while nothing under it has
        reached the accounts. Once any of its settlements has been posted, or has
        produced a subcontractor bill, a salesperson commission bill, a payment,
        a voucher, or is holding client invoices, deletion is blocked so the
        accounting trail and the links to those documents are never lost. This
        mirrors the protection already on the settlement line itself and the same
        rule core Accounting applies: reset or remove those documents first.
        """
        for rec in self:
            settlements = rec.settlement_ids
            blockers = []
            posted = settlements.filtered(lambda s: s.state != 'draft')
            if posted:
                blockers.append(_('%s posted settlement(s)') % len(posted))
            bills = settlements.mapped('bill_id')
            if bills:
                blockers.append(_('subcontractor bill(s) %s')
                                % ', '.join(bills.mapped('display_name')))
            sp_bills = settlements.mapped('salesperson_bill_id')
            if sp_bills:
                blockers.append(_('salesperson commission bill(s) %s')
                                % ', '.join(sp_bills.mapped('display_name')))
            payments = settlements.mapped('payment_id')
            if payments:
                blockers.append(_('payment(s) %s')
                                % ', '.join(payments.mapped('display_name')))
            vouchers = settlements.filtered(lambda s: s.voucher_number)
            if vouchers:
                blockers.append(_('%s generated voucher(s)') % len(vouchers))
            invoices = settlements.mapped('allocation_ids.invoice_id')
            if invoices:
                blockers.append(_('%s linked client invoice(s)') % len(invoices))
            if blockers:
                raise UserError(_(
                    'This Commissioning record cannot be deleted because it still '
                    'has %s. Removing it would break the accounting trail. Reset '
                    'those settlements to draft, and cancel or reverse the linked '
                    'bills, vouchers, payments and invoices in Accounting first.'
                ) % ', '.join(blockers))

    def _settings(self):
        return self.env['way4tech.payroll.settings'].get_for_company(
            self.company_id.id)
