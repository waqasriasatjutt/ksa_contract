# -*- coding: utf-8 -*-
"""CB1 (19.0.4.0.0) — Commissioning settlement lines + invoice allocations.

A settlement is one receipt/settlement event on a Commissioning record. It:
  * allocates the money received across the client's Commissioning invoices
    (FIFO, oldest first) — ``way4tech.commission.settlement.invoice``;
  * splits the ex-VAT receipt into AlZain's commission (~5%) and the
    subcontractor's 95% payable;
  * creates the subcontractor vendor bill for the GROSS 95% (Dr 520002 /
    Cr 210002), on the Commissioning purchases journal only;
  * pays it through a voucher that registers the cash payment AND recovers any
    subcontractor advance (142005) by reconciliation — standard tools only,
    scoped to this Commissioning bill, never a global account.move override;
  * optionally raises the salesperson commission on the realised gross profit.

Everything is driven by THIS line's own ``date`` — period, VAT and P&L all
follow it, never the header.
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CommissionSettlementInvoice(models.Model):
    _name = 'way4tech.commission.settlement.invoice'
    _description = 'Commissioning Settlement — Invoice Allocation'
    _order = 'invoice_date, id'

    settlement_id = fields.Many2one(
        'way4tech.commission.settlement', required=True, ondelete='cascade')
    invoice_id = fields.Many2one(
        'account.move', string='Client Invoice', required=True)
    invoice_date = fields.Date(related='invoice_id.invoice_date', store=True)
    invoice_total = fields.Monetary(
        related='invoice_id.amount_total', string='Invoice Total',
        currency_field='currency_id')
    allocated_amount = fields.Monetary(
        string='Allocated (incl. VAT)', currency_field='currency_id',
        help='Portion of this invoice consumed by this settlement (FIFO).')
    currency_id = fields.Many2one(
        related='settlement_id.currency_id', readonly=True)

    @api.model
    def _received_for_invoice(self, invoice, exclude_settlement=None):
        """Total already allocated against `invoice` by every settlement
        (optionally excluding one, so a settlement's own draft rows don't
        count against its own pending view)."""
        domain = [('invoice_id', '=', invoice.id)]
        if exclude_settlement:
            domain.append(('settlement_id', '!=', exclude_settlement.id))
        allocs = self.search(domain)
        return sum(allocs.mapped('allocated_amount'))


class CommissionSettlement(models.Model):
    _name = 'way4tech.commission.settlement'
    _description = 'Commissioning Settlement'
    _order = 'date desc, id desc'
    _rec_name = 'display_name'

    receipt_id = fields.Many2one(
        'way4tech.commission.receipt', string='Commissioning Record',
        required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        related='receipt_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one(
        related='receipt_id.company_id.currency_id', store=True, readonly=True)
    subcontractor_id = fields.Many2one(
        related='receipt_id.subcontractor_id', store=True, readonly=True)
    partner_id = fields.Many2one(
        related='receipt_id.partner_id', store=True, readonly=True,
        string='Client')

    date = fields.Date(
        string='Settlement Date', required=True,
        default=fields.Date.context_today, index=True,
        help='Drives all period/VAT/P&L reporting for this settlement.')
    display_name = fields.Char(compute='_compute_display_name_cb')

    allocation_ids = fields.One2many(
        'way4tech.commission.settlement.invoice', 'settlement_id',
        string='Client Invoices')

    # ── Receipt & commission (CB1 §6) ─────────────────────────────────────
    full_receipt_amount = fields.Monetary(
        string='Full Receipt Amount', currency_field='currency_id',
        help='Amount actually received (incl. VAT). Defaults to the selected '
             'invoices but is editable for partial receipts.')
    vat_rate = fields.Float(string='VAT %', default=15.0, digits=(5, 2))
    receipt_excl_vat = fields.Monetary(
        string='Receipt Ex-VAT', compute='_compute_amounts', store=True,
        currency_field='currency_id')
    commission_is_fix = fields.Boolean(string='Fix Commission')
    commission_percent = fields.Float(
        string='Commission %', digits=(5, 2), default=5.0)
    commission_fix = fields.Monetary(
        string='Fix Commission', currency_field='currency_id')
    commission_amount = fields.Monetary(
        string='Commission (Gross Profit)', compute='_compute_amounts',
        store=True, currency_field='currency_id')
    gross_payable = fields.Monetary(
        string='Gross Subcontractor Payable', compute='_compute_amounts',
        store=True, currency_field='currency_id',
        help='Ex-VAT receipt minus commission (= 95% of ex-VAT). The bill '
             'amount.')

    # ── Advance & outstanding (subcontractor level) ───────────────────────
    advance_balance = fields.Monetary(
        string='Advance Balance', compute='_compute_advance_balance',
        currency_field='currency_id',
        help='Subcontractor advance still outstanding (142005). Read-only.')
    advance_recovered = fields.Monetary(
        string='Advance Recovered', currency_field='currency_id',
        help='Advance offset against this payable at the voucher stage.')
    previous_outstanding = fields.Monetary(
        string='Previous Outstanding', compute='_compute_outstanding',
        currency_field='currency_id',
        help='Subcontractor amount from prior settlements not yet fully paid.')
    outstanding_paid = fields.Monetary(
        string='Outstanding Paid', currency_field='currency_id',
        help='Prior outstanding paid this time (FIFO against oldest bills).')
    net_payable = fields.Monetary(
        string='Net Subcontractor Payable', compute='_compute_amounts',
        store=True, currency_field='currency_id',
        help='Gross minus advance recovered — the cash paid on the bill.')
    consolidated_payable = fields.Monetary(
        string='Consolidated Payable', compute='_compute_amounts',
        store=True, currency_field='currency_id',
        help='Net plus prior outstanding paid — total cash out this voucher.')

    # ── Documents ─────────────────────────────────────────────────────────
    bill_id = fields.Many2one(
        'account.move', string='Subcontractor Bill', readonly=True, copy=False)
    payment_id = fields.Many2one(
        'account.payment', string='Payment Voucher', readonly=True, copy=False)
    voucher_number = fields.Char(string='Voucher No', readonly=True, copy=False)
    salesperson_bill_id = fields.Many2one(
        'account.move', string='Salesperson Commission Bill',
        readonly=True, copy=False)
    salesperson_commission_amount = fields.Monetary(
        string='Salesperson Commission', currency_field='currency_id',
        readonly=True, copy=False)

    state = fields.Selection(
        selection=[('draft', 'Draft'), ('billed', 'Bill Created'),
                   ('voucher', 'Voucher Generated')],
        string='Status', default='draft', copy=False,
        help='Voucher Generated is the confirmation point: advances are applied '
             'and the voucher is issued. The cash/bank payment is registered '
             'separately (before or after), and its status shows in Payment.')
    # Whether the cash/bank payment has been made shows here, read from the
    # bill. Payment is registered through the standard Register Payment wizard
    # (any bank or cash journal), so it stays independent of voucher issue.
    payment_status = fields.Selection(
        related='bill_id.payment_state', string='Payment', readonly=True)

    # ── Computed Data per client (CB1 §10) — read-only ────────────────────
    client_pending_count = fields.Integer(compute='_compute_client_pending')
    client_pending_names = fields.Char(compute='_compute_client_pending')
    client_pending_total = fields.Monetary(
        compute='_compute_client_pending', currency_field='currency_id')
    client_pending_vat = fields.Monetary(
        compute='_compute_client_pending', currency_field='currency_id')

    @api.depends('partner_id', 'company_id', 'allocation_ids.allocated_amount')
    def _compute_client_pending(self):
        Alloc = self.env['way4tech.commission.settlement.invoice']
        for rec in self:
            names, total, vat, cnt = [], 0.0, 0.0, 0
            if rec.partner_id:
                settings = rec.receipt_id._settings()
                domain = [('partner_id', '=', rec.partner_id.id),
                          ('move_type', '=', 'out_invoice'),
                          ('state', '=', 'posted'),
                          ('company_id', '=', rec.company_id.id)]
                if settings.commission_journal_id:
                    domain.append(('journal_id', '=', settings.commission_journal_id.id))
                for inv in self.env['account.move'].search(domain):
                    received = Alloc._received_for_invoice(inv, exclude_settlement=rec)
                    pending = (inv.amount_total or 0.0) - received
                    if pending > 0.005:
                        cnt += 1
                        names.append(inv.name or '')
                        total += pending
                        if inv.amount_total:
                            vat += (inv.amount_tax or 0.0) * (pending / inv.amount_total)
            rec.client_pending_count = cnt
            rec.client_pending_names = ', '.join(names)
            rec.client_pending_total = total
            rec.client_pending_vat = vat

    # ── Display name ──────────────────────────────────────────────────────
    @api.depends('receipt_id.reference', 'date')
    def _compute_display_name_cb(self):
        for rec in self:
            base = rec.receipt_id.reference or rec.receipt_id.name or _('Settlement')
            rec.display_name = '%s / %s' % (base, rec.date or '')

    # ── Amount computes (CB1 §6) ──────────────────────────────────────────
    @api.depends('full_receipt_amount', 'vat_rate', 'commission_is_fix',
                 'commission_percent', 'commission_fix', 'advance_recovered',
                 'outstanding_paid', 'allocation_ids')
    def _compute_amounts(self):
        for rec in self:
            divisor = 1.0 + (rec.vat_rate or 0.0) / 100.0
            excl = rec.full_receipt_amount / divisor if divisor else rec.full_receipt_amount
            if rec.commission_is_fix:
                # CB1 R(new) item 4: a fixed rate applies once PER selected
                # invoice. max(..,1) keeps the single-invoice / not-yet-selected
                # case at the plain fix amount (no regression). The Gross Profit
                # % branch below is unchanged.
                commission = (rec.commission_fix or 0.0) * max(len(rec.allocation_ids), 1)
            else:
                commission = excl * (rec.commission_percent or 0.0) / 100.0
            # Once a subcontractor bill exists, its ex-VAT / commission / gross
            # were posted as they stood — never let a later formula change or
            # edit drift those three from the posted bill. Net and Consolidated
            # STILL recompute, because advance_recovered / outstanding_paid are
            # entered at the billed stage (editable until the voucher) and must
            # flow through live to the voucher figures.
            if not rec.bill_id:
                rec.receipt_excl_vat = excl
                rec.commission_amount = commission
                rec.gross_payable = excl - commission
            rec.net_payable = rec.gross_payable - (rec.advance_recovered or 0.0)
            rec.consolidated_payable = rec.net_payable + (rec.outstanding_paid or 0.0)

    def _advance_account(self):
        return self.receipt_id._settings().subcontractor_advance_account_id

    @api.depends('subcontractor_id', 'company_id')
    def _compute_advance_balance(self):
        for rec in self:
            acc = rec._advance_account()
            bal = 0.0
            if acc and rec.subcontractor_id:
                # Advance is a receivable (Dr) balance on 142005 for this sub.
                # ORM search (not raw SQL) so pending writes are flushed first
                # and the balance reflects entries posted earlier in the request.
                lines = self.env['account.move.line'].search([
                    ('account_id', '=', acc.id),
                    ('partner_id', '=', rec.subcontractor_id.id),
                    ('company_id', '=', rec.company_id.id),
                    ('parent_state', '=', 'posted'),
                ])
                bal = sum(lines.mapped('balance'))
            rec.advance_balance = bal

    @api.depends('subcontractor_id', 'company_id', 'date')
    def _compute_outstanding(self):
        """Prior settlements' bills for this subcontractor still open."""
        for rec in self:
            out = 0.0
            prior = rec.search([
                ('subcontractor_id', '=', rec.subcontractor_id.id),
                ('company_id', '=', rec.company_id.id),
                ('id', '!=', rec.id or 0),
                ('bill_id', '!=', False),
            ])
            for p in prior:
                bill = p.bill_id
                if bill.state == 'posted' and bill.payment_state not in ('paid', 'reversed'):
                    out += bill.amount_residual
            rec.previous_outstanding = out

    # ── Defaults from header when a settlement is added ────────────────────
    @api.onchange('receipt_id')
    def _onchange_receipt_defaults(self):
        if self.receipt_id:
            self.commission_is_fix = self.receipt_id.commission_is_fix
            self.commission_percent = self.receipt_id.commission_percent or 5.0
            self.commission_fix = self.receipt_id.commission_fix

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('receipt_id') and 'commission_percent' not in vals:
                rec = self.env['way4tech.commission.receipt'].browse(vals['receipt_id'])
                vals.setdefault('commission_is_fix', rec.commission_is_fix)
                vals.setdefault('commission_percent', rec.commission_percent or 5.0)
                vals.setdefault('commission_fix', rec.commission_fix)
        return super().create(vals_list)

    # ── FIFO allocation across the selected invoices (CB1 §7) ─────────────
    def _reallocate_fifo(self):
        """Spread full_receipt_amount over the allocated invoices oldest-first,
        each capped at its own remaining pending (pending against OTHER
        settlements, so re-running is idempotent). A combined partial receipt
        clears the oldest invoices fully and leaves the newest short."""
        Alloc = self.env['way4tech.commission.settlement.invoice']
        for rec in self:
            remaining = rec.full_receipt_amount or 0.0
            allocs = rec.allocation_ids.sorted(
                lambda a: (a.invoice_date or fields.Date.today(), a.id))
            for a in allocs:
                inv = a.invoice_id
                others = Alloc._received_for_invoice(inv, exclude_settlement=rec)
                invoice_pending = (inv.amount_total or 0.0) - others
                take = max(min(remaining, invoice_pending), 0.0)
                a.allocated_amount = take
                remaining -= take

    @api.onchange('full_receipt_amount')
    def _onchange_full_receipt_reallocate(self):
        if self.allocation_ids:
            self._reallocate_fifo()

    # ── CB1 R4: protect processed settlements from deletion ───────────────
    @api.ondelete(at_uninstall=False)
    def _unlink_protect_processed(self):
        """A settlement can be edited or removed only while it is still Draft
        with no accounting documents generated. Once it has produced a
        subcontractor bill, a payment voucher, or a salesperson commission
        bill, deletion is blocked so the accounting trail and the links to
        those documents are never lost. Fires on every delete path, including
        removing the line from the record's Settlements list. Mirrors the
        Manpower line-delete protection."""
        for rec in self:
            blockers = []
            if rec.bill_id:
                blockers.append(_('subcontractor bill %s') % (rec.bill_id.name or rec.bill_id.display_name or ''))
            if rec.salesperson_bill_id:
                blockers.append(_('salesperson commission bill %s') % (rec.salesperson_bill_id.name or rec.salesperson_bill_id.display_name or ''))
            if rec.payment_id:
                blockers.append(_('payment %s') % (rec.payment_id.name or rec.payment_id.display_name or ''))
            # C4 (2026-08): block ONLY on LIVE document references — the
            # subcontractor bill, the salesperson bill, or a real payment. The
            # voucher_number is just a printed confirmation STAMP, not itself an
            # accounting document, so it is NOT a blocker on its own. Previously
            # it was: after a user reset+deleted the bill (state sync nulls
            # bill_id and reverts to draft) the stray voucher_number lingered and
            # kept blocking deletion even though nothing real remained, forcing
            # them to scrap the whole project. Now, while a bill/payment exists
            # its FK blocks (a genuine voucher stays fully protected); once they
            # are gone the stamp alone no longer blocks. (Residual: an advance-
            # recovery journal entry, if one was posted at voucher time, lives in
            # Accounting on its own and is not linked here — review/reverse it in
            # Accounting when scrapping a settlement that had recovered advances.)
            if blockers:
                raise UserError(_(
                    'This settlement has already generated accounting documents '
                    '(%s) and cannot be deleted. Removing it would break the '
                    'accounting trail. If you genuinely need to remove it, cancel '
                    'or reverse those documents in Accounting first.'
                ) % ', '.join(blockers))

    # ── Invoice-selection wizard opener (CB1 §5) ──────────────────────────
    def action_select_invoices(self):
        self.ensure_one()
        if not self.receipt_id.partner_id:
            raise UserError(_('Set the client on the record first.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Select Client Invoices'),
            'res_model': 'way4tech.commission.invoice.select.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_settlement_id': self.id},
        }

    # ── Subcontractor bill (CB1 §4.3 / §1 postings) ───────────────────────
    def _require(self, settings, field, label):
        val = getattr(settings, field)
        if not val:
            raise UserError(_(
                'Commissioning is not fully configured: "%s" is blank. Set it '
                'in Configuration > Payroll & Accounting Setup > Commissioning '
                'before creating this document.') % label)
        return val

    def action_create_bill(self):
        self.ensure_one()
        if self.bill_id:
            raise UserError(_('A subcontractor bill already exists.'))
        if self.gross_payable <= 0:
            raise UserError(_('Gross payable is zero — nothing to bill.'))
        # Re-run the FIFO split from the current (possibly overridden) Full
        # Receipt Amount so the per-invoice allocation is correct at billing,
        # independent of any form onchange. gross_payable itself is computed
        # from full_receipt_amount, so the bill always follows the override.
        self._reallocate_fifo()
        settings = self.receipt_id._settings()
        expense = self._require(settings, 'subcontractor_expense_account_id',
                                'Subcontractor Payable Account (Expense)')
        payable = self._require(settings, 'commissioning_payable_account_id',
                                'Commissioning Subcontractor Payable')
        journal = self._require(settings, 'commissioning_purchase_journal_id',
                                'Commissioning Purchases Journal')
        line_vals = {
            'name': _('Subcontractor share - %s') % (self.receipt_id.reference or ''),
            'quantity': 1.0,
            'price_unit': self.gross_payable,
            'account_id': expense.id,
        }
        if self.receipt_id.analytic_distribution:
            line_vals['analytic_distribution'] = self.receipt_id.analytic_distribution
        # C3 (2026-08): trace the bill back to the client invoice(s) it was
        # generated from — put their number(s) in Payment Reference. Uses the
        # invoices this settlement actually allocated against; falls back to the
        # SUB reference so the field is never blank. Only affects bills created
        # through this Commissioning flow.
        _sel_invoices = self.allocation_ids.filtered(
            lambda a: (a.allocated_amount or 0.0) > 0
        ).mapped('invoice_id')
        _inv_numbers = ', '.join(i.name for i in _sel_invoices if i.name)
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.subcontractor_id.id,
            'invoice_date': self.date,
            'date': self.date,
            'company_id': self.company_id.id,
            'journal_id': journal.id,
            'ref': self.receipt_id.reference or '',
            'payment_reference': _inv_numbers or (self.receipt_id.reference or ''),
            'invoice_line_ids': [(0, 0, line_vals)],
        }
        if self.receipt_id.way4tech_project_id:
            bill_vals['way4tech_project_id'] = self.receipt_id.way4tech_project_id.id
        if self.receipt_id.way4tech_category_id:
            bill_vals['way4tech_category_id'] = self.receipt_id.way4tech_category_id.id
        if self.receipt_id.tag_ids:
            bill_vals['way4tech_tag_ids'] = [(6, 0, self.receipt_id.tag_ids.ids)]
        bill = self.env['account.move'].create(bill_vals)
        # Force the payable (credit) line onto the Commissioning payable
        # account (210002) instead of the partner's generic AP — scoped to
        # THIS bill only, so the Commissioning payable is isolated from any
        # Manpower payable the same subcontractor may carry.
        term_lines = bill.line_ids.filtered(
            lambda l: l.display_type == 'payment_term')
        if term_lines:
            term_lines.account_id = payable.id
        bill.action_post()
        self.write({'bill_id': bill.id, 'state': 'billed'})
        return self._open_move(bill, _('Subcontractor Bill'))

    # ── Generate Payment Voucher (CB1 R2 item 2) ──────────────────────────
    # Voucher generation is the CONFIRMATION event, like issuing a cheque. It
    # applies the advance recovery immediately and issues the voucher number.
    # It does NOT move cash — the bank/cash payment is registered separately
    # (before or after) through the standard wizard, so voucher issue never
    # depends on the payment being completed.
    def action_generate_voucher(self):
        self.ensure_one()
        if not self.bill_id or self.bill_id.state != 'posted':
            raise UserError(_('Create and post the subcontractor bill first.'))
        if self.voucher_number:
            raise UserError(_('The voucher has already been generated for this settlement.'))
        settings = self.receipt_id._settings()
        adv_recovered = min(self.advance_recovered or 0.0,
                            self.gross_payable, max(self.advance_balance, 0.0))
        # Advance recovery: Dr 210002 / Cr 142005, reconciled against the bill,
        # so the bill's remaining balance becomes the net cash still to pay.
        if adv_recovered > 0:
            self._apply_advance_recovery(settings, adv_recovered)
        self.write({
            'voucher_number': self._next_voucher_number(),
            'state': 'voucher',
        })
        return self.action_print_voucher()

    # ── Register Payment (CB1 R2 item 3) ──────────────────────────────────
    # Opens the STANDARD payment register wizard so the user chooses the
    # payment source (SNB, any other bank, petty cash, any bank/cash journal)
    # and the amount before confirming. Can be run before or after the voucher.
    def action_register_payment(self):
        self.ensure_one()
        if not self.bill_id or self.bill_id.state != 'posted':
            raise UserError(_('Create and post the subcontractor bill first.'))
        if self.bill_id.payment_state in ('paid', 'in_payment'):
            raise UserError(_('This bill is already paid.'))
        return {
            'name': _('Register Payment'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'view_id': self.env.ref('account.view_account_payment_register_form').id,
            'target': 'new',
            'context': {
                'active_model': 'account.move',
                'active_ids': self.bill_id.ids,
            },
        }

    def _apply_advance_recovery(self, settings, amount):
        """Dr 210002 / Cr 142005 for `amount`, then reconcile the Dr-210002
        leg against the bill's still-open payable — settling the bill from the
        advance and drawing 142005 down. Standard misc entry + reconcile."""
        payable = settings.commissioning_payable_account_id
        advance = settings.subcontractor_advance_account_id
        if not (payable and advance):
            raise UserError(_('Configure the Commissioning payable and advance accounts first.'))
        gen = self.env['account.journal'].search([
            ('type', '=', 'general'), ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not gen:
            raise UserError(_('No general journal to post the advance recovery.'))
        entry = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': gen.id,
            'date': self.date,
            'company_id': self.company_id.id,
            'ref': _('Advance recovery - %s') % (self.receipt_id.reference or ''),
            'line_ids': [
                (0, 0, {'account_id': payable.id, 'partner_id': self.subcontractor_id.id,
                        'debit': amount, 'credit': 0.0,
                        'name': _('Advance recovery')}),
                (0, 0, {'account_id': advance.id, 'partner_id': self.subcontractor_id.id,
                        'debit': 0.0, 'credit': amount,
                        'name': _('Advance recovery')}),
            ],
        })
        entry.action_post()
        # Reconcile the payable legs (bill open payable + this debit).
        to_rec = (self.bill_id.line_ids + entry.line_ids).filtered(
            lambda l: l.account_id == payable and not l.reconciled
            and l.partner_id == self.subcontractor_id)
        if to_rec:
            to_rec.reconcile()

    @api.model
    def _next_voucher_number(self):
        prefix = 'VOU/%s/' % fields.Date.context_today(self).strftime('%Y/%m')
        highest = 0
        for other in self.search([('voucher_number', '=like', prefix + '%')]):
            tail = (other.voucher_number or '').rsplit('/', 1)[-1]
            if tail.isdigit():
                highest = max(highest, int(tail))
        return '%s%04d' % (prefix, highest + 1)

    # ── Salesperson commission (CB1 §11) ──────────────────────────────────
    def action_create_salesperson_commission(self):
        self.ensure_one()
        emp = self.receipt_id.salesperson_id
        if not emp:
            raise UserError(_('No salesperson set on this record.'))
        if self.salesperson_bill_id:
            raise UserError(_('Salesperson commission already created for this settlement.'))
        settings = self.receipt_id._settings()
        rule = settings.commissioning_salesperson_rule_ids.filtered(
            lambda r: r.employee_id == emp)[:1]
        if not rule:
            raise UserError(_(
                'No Commissioning salesperson rule for "%s". Add it in '
                'Configuration > Payroll & Accounting Setup > Commissioning.'
            ) % emp.name)
        if rule.mode == 'fix':
            # Fix amount is per client, applied ONCE — not per invoice count.
            already = self.search([
                ('receipt_id', '=', self.receipt_id.id),
                ('salesperson_bill_id', '!=', False)])
            if already:
                raise UserError(_(
                    'Fix salesperson commission is once per client and was '
                    'already raised on this record.'))
            amount = rule.fix_amount or 0.0
        else:
            amount = self.commission_amount * (rule.percent or 0.0) / 100.0
        if amount <= 0:
            raise UserError(_('Computed salesperson commission is zero.'))
        payee = emp.user_id.partner_id or getattr(emp, 'work_contact_id', False)
        if not payee:
            raise UserError(_(
                'Salesperson "%s" has no linked partner (user or work contact) '
                'to bill the commission to.') % emp.name)
        expense = settings.commission_expense_account_id
        if not expense:
            raise UserError(_('Set the Sales Person Commission Expense Account in settings.'))
        journal = settings.commissioning_purchase_journal_id or \
            self.env['account.journal'].search(
                [('type', '=', 'purchase'), ('company_id', '=', self.company_id.id)], limit=1)
        line_vals = {
            'name': _('Salesperson commission - %s') % (self.receipt_id.reference or ''),
            'quantity': 1.0, 'price_unit': amount, 'account_id': expense.id,
        }
        if self.receipt_id.analytic_distribution:
            line_vals['analytic_distribution'] = self.receipt_id.analytic_distribution
        bill = self.env['account.move'].create({
            'move_type': 'in_invoice',
            'partner_id': payee.id,
            'invoice_date': self.date,
            'date': self.date,
            'company_id': self.company_id.id,
            'journal_id': journal.id if journal else False,
            'ref': _('Salesperson commission %s') % (self.receipt_id.reference or ''),
            'invoice_line_ids': [(0, 0, line_vals)],
        })
        self.write({'salesperson_bill_id': bill.id,
                    'salesperson_commission_amount': amount})
        return self._open_move(bill, _('Salesperson Commission Bill'))

    # ── helpers ───────────────────────────────────────────────────────────
    def _open_move(self, move, name):
        return {
            'type': 'ir.actions.act_window', 'name': name,
            'res_model': 'account.move', 'res_id': move.id,
            'view_mode': 'form', 'target': 'current',
        }

    def _open_payment(self, payment):
        return {
            'type': 'ir.actions.act_window', 'name': _('Payment Voucher'),
            'res_model': 'account.payment', 'res_id': payment.id,
            'view_mode': 'form', 'target': 'current',
        }

    def action_print_voucher(self):
        return self.env.ref(
            'way4tech_logistics.action_report_commissioning_voucher'
        ).report_action(self)
