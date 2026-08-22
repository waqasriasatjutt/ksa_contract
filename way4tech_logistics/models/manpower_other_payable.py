# -*- coding: utf-8 -*-
"""Part 1 (2026-08) — Other Payable tab on the Manpower Contract.

Some expense categories are (correctly) mapped in Payroll & Accounting Setup to
a Payable/Liability GL account — e.g. "Own Driver Salary" -> 260005 "Logistic
Driver Salary Payable". A vendor BILL can never post to a payable account, so
the Direct Cost / Operating Exp tabs reject them ("No expense account
configured"). This tab records those costs as a balanced JOURNAL ENTRY instead
(Dr a shared cost account / Cr the mapped payable), which can post to any
account type.

Mirrors the Direct/Operating structure — a per-line model plus a block that
combines several lines into ONE journal entry — with the same attachments, live
payment status, approval gate and Billing-Summary integration. Routing is
automatic by the mapped account's TYPE, reusing the EXISTING category map; no new
configuration table, and nothing about Direct Cost / Operating Exp changes.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_PAYABLE_TYPES = ('liability_payable', 'liability_current',
                  'liability_non_current')


class Way4TechManpowerOtherPayable(models.Model):
    _name = 'way4tech.manpower.other.payable'
    _description = 'Manpower Contract — Other Payable Line'
    _inherit = ['mail.thread', 'mail.activity.mixin',
                'way4tech.manpower.approval.mixin',
                'way4tech.manpower.docline.mixin']
    _order = 'date desc, id desc'
    _way4tech_attach_view_xmlid = \
        'way4tech_logistics.view_other_payable_line_attach_form'

    contract_id = fields.Many2one(
        'way4tech.manpower.contract', string='Contract',
        required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        related='contract_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one(
        related='contract_id.company_id.currency_id', store=True, readonly=True)
    date = fields.Date(
        string='Date', default=fields.Date.context_today, required=True)
    description = fields.Char(string='Description')
    category_id = fields.Many2one(
        'way4tech.expense.category', string='Category',
        help='A category whose mapped account is a Payable/Liability type. The '
             'Payable account auto-fills from the existing map.')
    partner_id = fields.Many2one(
        'res.partner', string='Employee / Party',
        help='Who or what this payable relates to (driver, employee, party).')
    account_id = fields.Many2one(
        'account.account', string='Expense Account',
        help='Auto-filled from the category map — the DEBIT (cost) side of the '
             'journal entry. Editable: you may override it. The CREDIT side is '
             'the Other Payable Cost Account configured in settings.')
    amount = fields.Monetary(string='Amount', currency_field='currency_id')
    other_payable_block_id = fields.Many2one(
        'way4tech.manpower.other.payable.block', ondelete='set null',
        index=True, copy=False)
    move_id = fields.Many2one(
        'account.move', string='Journal Entry', readonly=True, copy=False)
    state = fields.Selection(
        [('draft', 'Draft'), ('posted', 'Posted')],
        default='draft', copy=False, index=True)

    # ── docline mixin binds to move_id (not invoice_id/bill_id) ───────────
    def _way4tech_document(self):
        self.ensure_one()
        return self.move_id

    @api.depends('move_id')
    def _compute_has_document(self):
        for rec in self:
            rec.has_document = bool(rec.move_id)

    @api.depends('move_id', 'move_id.state',
                 'move_id.line_ids.amount_residual',
                 'move_id.line_ids.reconciled')
    def _compute_way4tech_payment_status(self):
        # A journal entry carries no invoice payment_state, so derive
        # Unpaid / Partially / Fully paid from reconciliation of its PAYABLE leg.
        for rec in self:
            rec.way4tech_payment_status = _je_payment_status(rec.move_id)

    @api.onchange('category_id')
    def _onchange_category_id(self):
        if not self.category_id:
            return
        company = self.company_id or self.env.company
        # Item 1 (2026-08): the DEBIT account auto-fills from the category's
        # EXPENSE mapping (the same map Direct Cost / Operating Exp use). The
        # CREDIT (payable) is the global Other Payable Cost Account, applied at
        # posting. Field stays editable so the user can override.
        acc = self.category_id.resolve_expense_account(company)
        self.account_id = acc or False
        if not acc:
            return {'warning': {
                'title': _('No account mapped'),
                'message': _(
                    'Category "%s" has no expense account mapped for this '
                    'company. Map it in Configuration → Payroll & Accounting '
                    'Setup → Manpower → Expense Category map.'
                ) % self.category_id.display_name}}

    def action_create_journal_entry(self):
        self.ensure_one()
        if self.other_payable_block_id:
            raise UserError(_(
                'This line belongs to an Other Payable block — post the combined '
                'journal entry from the block instead.'))
        if self.move_id:
            raise UserError(_('A journal entry already exists for this line.'))
        if not (self.amount or 0.0):
            raise UserError(_('Set an amount before posting the journal entry.'))
        contract = self.contract_id
        contract._require_month_approval(record=self)
        debit_acct = self.account_id or self.category_id.resolve_expense_account(
            contract.company_id, raise_if_missing=True)
        move = self.env['way4tech.manpower.other.payable.block']._post_journal_entry(
            contract=contract, party=self.partner_id, date=self.date,
            lines=[(debit_acct, self.description, self.amount)],
            ref=_('Other Payable — %s') % (contract.name or ''))
        self.write({'move_id': move.id, 'state': 'posted'})
        contract._consume_approval(self)
        return _open_move(self, move)

    def action_view_move(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_('No journal entry has been created yet.'))
        return _open_move(self, self.move_id)

    def unlink(self):
        for rec in self:
            if rec.move_id and rec.move_id.state == 'posted':
                raise UserError(_(
                    'This line has a posted journal entry (%s). Reverse or delete '
                    'that entry in Accounting first.'
                ) % (rec.move_id.name or rec.move_id.id))
        return super().unlink()


class Way4TechManpowerOtherPayableBlock(models.Model):
    _name = 'way4tech.manpower.other.payable.block'
    _description = 'Manpower Contract — Other Payable Block (Journal Entry)'
    _inherit = ['way4tech.manpower.approval.mixin',
                'way4tech.manpower.docline.mixin']
    _order = 'date desc, id desc'
    _way4tech_attach_view_xmlid = \
        'way4tech_logistics.view_other_payable_block_attach_form'

    name = fields.Char(compute='_compute_name')
    contract_id = fields.Many2one(
        'way4tech.manpower.contract', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(
        related='contract_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one(
        related='contract_id.company_id.currency_id', store=True, readonly=True)
    partner_id = fields.Many2one('res.partner', string='Employee / Party')
    date = fields.Date(default=fields.Date.context_today, required=True)
    line_ids = fields.One2many(
        'way4tech.manpower.other.payable', 'other_payable_block_id',
        string='Other Payable Lines')
    line_count = fields.Integer(compute='_compute_totals')
    amount_total = fields.Monetary(
        compute='_compute_totals', currency_field='currency_id')
    move_id = fields.Many2one(
        'account.move', string='Journal Entry', readonly=True, copy=False)
    state = fields.Selection(
        [('draft', 'Draft'), ('posted', 'Posted')],
        default='draft', copy=False, index=True)

    def _compute_name(self):
        for rec in self:
            nm = rec.move_id.name if (rec.move_id and rec.move_id.name != '/') else False
            rec.name = nm or ((_('Other Payable Block #%s') % rec.id)
                              if rec.id else _('Other Payable Block'))

    @api.depends('line_ids.amount')
    def _compute_totals(self):
        for rec in self:
            rec.line_count = len(rec.line_ids)
            rec.amount_total = sum(rec.line_ids.mapped('amount'))

    def _way4tech_document(self):
        self.ensure_one()
        return self.move_id

    @api.depends('move_id')
    def _compute_has_document(self):
        for rec in self:
            rec.has_document = bool(rec.move_id)

    @api.depends('move_id', 'move_id.state',
                 'move_id.line_ids.amount_residual',
                 'move_id.line_ids.reconciled')
    def _compute_way4tech_payment_status(self):
        for rec in self:
            rec.way4tech_payment_status = _je_payment_status(rec.move_id)

    def write(self, vals):
        # Void a standing approval when the party or date changes after approval.
        if {'partner_id', 'date'} & set(vals):
            self.env['way4tech.manpower.approval.request']._invalidate_for(self)
        return super().write(vals)

    @api.model
    def _post_journal_entry(self, contract, party, date, lines, ref):
        """Create + POST one balanced journal entry for `lines` (tuples of
        (debit_account, description, amount)): Dr each line's EXPENSE account
        (from the category map) / Cr the shared Other Payable Cost Account (the
        payable). Standard account.move only."""
        company = contract.company_id
        settings = self.env['way4tech.payroll.settings'].get_for_company(company.id)
        journal = settings.manpower_other_payable_journal_id or \
            self.env['account.journal'].search(
                [('type', '=', 'general'), ('company_id', '=', company.id)], limit=1)
        if not journal:
            raise UserError(_(
                'No General journal for company "%s". Set an Other Payable '
                'Journal in Payroll & Accounting Setup.') % company.display_name)
        credit_acct = settings.manpower_other_payable_cost_account_id
        if not credit_acct:
            raise UserError(_(
                'Set the "Other Payable Cost Account" in Configuration → Payroll '
                '& Accounting Setup → Manpower Contracts. It is the account '
                'CREDITED on every Other Payable journal entry (the debit is the '
                'category\'s own expense account).'))
        move_lines = []
        for debit_acct, desc, amount in lines:
            if not debit_acct:
                raise UserError(_(
                    'An Other Payable line has no expense account. Map its '
                    'category to an account in Payroll & Accounting Setup → '
                    'Expense Category map, or set the account on the line.'))
            if not amount:
                continue
            nm = desc or (debit_acct.name or '')
            pid = party.id if party else False
            move_lines.append((0, 0, {
                'account_id': debit_acct.id, 'partner_id': pid,
                'debit': amount, 'credit': 0.0, 'name': nm}))
            move_lines.append((0, 0, {
                'account_id': credit_acct.id, 'partner_id': pid,
                'debit': 0.0, 'credit': amount, 'name': nm}))
        if not move_lines:
            raise UserError(_('Nothing to post — every line has a zero amount.'))
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': date,
            'company_id': company.id,
            'ref': ref,
            'line_ids': move_lines,
        })
        if 'way4tech_project_id' in move._fields and contract.way4tech_project_id:
            move.way4tech_project_id = contract.way4tech_project_id.id
        if 'way4tech_category_id' in move._fields and contract.way4tech_category_id:
            move.way4tech_category_id = contract.way4tech_category_id.id
        move.action_post()
        return move

    def action_create_journal_entry(self):
        self.ensure_one()
        if self.move_id:
            raise UserError(_('This block already produced a journal entry.'))
        if not self.line_ids:
            raise UserError(_('Add at least one line before posting.'))
        contract = self.contract_id
        contract._require_month_approval(record=self)
        move = self._post_journal_entry(
            contract=contract, party=self.partner_id, date=self.date,
            lines=[(l.account_id or l.category_id.resolve_expense_account(
                        contract.company_id, raise_if_missing=True),
                    l.description, l.amount) for l in self.line_ids],
            ref=_('Other Payable — %s') % (contract.name or ''))
        self.line_ids.write({'move_id': move.id, 'state': 'posted'})
        self.write({'move_id': move.id, 'state': 'posted'})
        contract._consume_approval(self)
        return _open_move(self, move)

    def action_view_move(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_('No journal entry has been created yet.'))
        return _open_move(self, self.move_id)

    def unlink(self):
        for rec in self:
            if rec.move_id and rec.move_id.state == 'posted':
                raise UserError(_(
                    'This block has a posted journal entry (%s). Reverse it in '
                    'Accounting first.') % (rec.move_id.name or rec.move_id.id))
        return super().unlink()


def _je_payment_status(move):
    """Unpaid / Partially / Fully paid for a journal entry, from reconciliation
    of its Payable leg(s). Returns False for an unposted/absent move."""
    if not move or move.state != 'posted':
        return False
    legs = move.line_ids.filtered(
        lambda l: l.account_id.account_type in _PAYABLE_TYPES)
    total = sum(abs(l.balance) for l in legs)
    residual = sum(abs(l.amount_residual) for l in legs)
    if not total:
        return False
    if residual <= 0.0001:
        return 'paid'
    if residual < total - 0.0001:
        return 'partial'
    return 'unpaid'


def _open_move(rec, move):
    return {
        'type': 'ir.actions.act_window', 'name': _('Journal Entry'),
        'res_model': 'account.move', 'res_id': move.id,
        'view_mode': 'form', 'target': 'current',
    }
