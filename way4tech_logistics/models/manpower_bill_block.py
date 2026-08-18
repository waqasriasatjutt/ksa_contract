# -*- coding: utf-8 -*-
"""Item 4 (2026-08) — Bill Block: several Direct Cost / Operating Exp lines on
ONE vendor bill. The vendor-bill mirror of the Project Income *invoice block*.

Before this, every Project Direct Cost / Operating Exp row minted its own
single-line vendor bill, so one supplier billing three cost items meant three
separate bills. A *bill block* groups several expense lines for ONE vendor and
produces ONE multi-line vendor bill.

Single-vendor by construction: a vendor bill (account.move) carries exactly one
partner, so the block has its own ``vendor_id`` and every line it bills goes to
that vendor. The existing per-line "Create Bill" button is completely untouched
and remains the path for standalone single-line bills — this is a pure,
optional addition sitting alongside it.

Nothing about how bills post to the GL changes: each line keeps its own expense
account, per-category Input VAT, analytic distribution, the contract's Project /
Entry Category / Tags, the Direct-Cost invoice-first rule and the purchase
journal — all reused from the existing single-line path. Like that path, the
bill is created in DRAFT (the accountant posts it in Accounting).
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class Way4TechManpowerBillBlock(models.Model):
    _name = 'way4tech.manpower.bill.block'
    _description = 'Manpower Contract — Bill Block (multi-line vendor bill)'
    _inherit = ['way4tech.manpower.approval.mixin',
                'way4tech.manpower.docline.mixin']
    # Newest first; never order by an editable date field (documented
    # date-picker re-focus loop).
    _order = 'id desc'

    name = fields.Char(
        string='Bill Block', compute='_compute_name', store=True,
        help='Auto-generated label. Shows the created vendor bill number once '
             'the block has been billed.',
    )
    contract_id = fields.Many2one(
        'way4tech.manpower.contract', string='Contract',
        required=True, ondelete='cascade', index=True,
    )
    company_id = fields.Many2one(
        related='contract_id.company_id', store=True, readonly=True,
    )
    currency_id = fields.Many2one(
        related='contract_id.currency_id', store=True, readonly=True,
    )
    # Which notebook tab this block lives on. Set from the tab context on
    # create; drives the Direct-Cost invoice-first rule and, in the view, keeps
    # a block on its own tab — mirroring how the flat lists are split.
    bucket = fields.Selection(
        [('direct', 'Direct Cost'), ('operating', 'Operating Exp')],
        string='Cost Type', required=True, default='direct',
    )
    vendor_id = fields.Many2one(
        'res.partner', string='Vendor', required=True, tracking=True,
        # Item 1 rationale — no hard supplier_rank domain; the view sets
        # res_partner_search_mode='supplier' so a just-created contact is
        # selectable and real vendors rank first.
        help='The single supplier this combined bill is raised to. Every line '
             'in the block is billed to this vendor — a vendor bill carries '
             'one partner.',
    )
    date = fields.Date(
        string='Accounting Date', required=True,
        default=lambda self: self._way4tech_default_period_date(),
        help='Posting date (account.move.date) of the vendor bill this block '
             'creates.',
    )
    bill_date = fields.Date(
        string='Bill Date', required=True, default=fields.Date.context_today,
        help='Vendor invoice date (account.move.invoice_date) of the bill this '
             'block creates.',
    )
    line_ids = fields.One2many(
        'way4tech.manpower.project.expense', 'bill_block_id',
        string='Bill Lines',
        help='Every row here becomes one line on the SAME vendor bill.',
    )
    line_count = fields.Integer(
        string='Lines', compute='_compute_totals', store=True,
    )
    amount_untaxed = fields.Monetary(
        string='Untaxed Total', compute='_compute_totals', store=True,
        currency_field='currency_id',
    )
    amount_tax = fields.Monetary(
        string='Input VAT', compute='_compute_totals', store=True,
        currency_field='currency_id',
        help='Sum of the per-category Input VAT that will apply when this block '
             'is billed.',
    )
    amount_total = fields.Monetary(
        string='Total', compute='_compute_totals', store=True,
        currency_field='currency_id',
        help='Gross total including Input VAT — the amount the bill will carry.',
    )
    bill_id = fields.Many2one(
        'account.move', string='Vendor Bill', readonly=True, copy=False,
    )
    # Three states, mirroring the invoice block. 'invoice_draft' is the middle
    # ground when the linked bill is reset to draft in Accounting (shown as
    # "Bill Draft"): still linked, showing View Bill, waiting to be re-posted.
    state = fields.Selection(
        [('draft', 'Draft'),
         ('invoice_draft', 'Bill Draft'),
         ('billed', 'Bill Created')],
        default='draft', readonly=True, copy=False,
    )

    @api.depends('bill_id', 'bill_id.name', 'date', 'state')
    def _compute_name(self):
        for block in self:
            # A draft account.move shows name '/', so treat that as "no number
            # yet" — the bill is created in draft and only gets its real number
            # when the accountant posts it (this compute follows bill_id.name).
            bill_name = block.bill_id.name if block.bill_id else False
            if bill_name and bill_name != '/':
                block.name = bill_name
            elif block.date:
                block.name = _('Draft Bill — %s') % block.date.strftime('%d/%m/%Y')
            else:
                block.name = _('Draft Bill')

    def _way4tech_line_input_vat(self, line, settings):
        """The Input VAT tax mapped to this expense line's category (or empty).
        Same source the single-line path reads in project.expense."""
        row = settings.manpower_expense_category_account_ids.filtered(
            lambda m: m.category_id == line.category_id
        )[:1]
        return row.input_vat_tax_id if row else self.env['account.tax']

    @api.depends('line_ids', 'line_ids.amount', 'line_ids.category_id',
                 'contract_id.company_id')
    def _compute_totals(self):
        for block in self:
            block.line_count = len(block.line_ids)
            untaxed = sum(block.line_ids.mapped('amount'))
            block.amount_untaxed = untaxed
            tax_total = 0.0
            if block.line_ids:
                settings = self.env['way4tech.payroll.settings'].get_for_company(
                    (block.company_id or self.env.company).id)
                for line in block.line_ids:
                    tax = block._way4tech_line_input_vat(line, settings)
                    if tax:
                        tax_total += (tax.amount / 100.0) * (line.amount or 0.0)
            block.amount_tax = tax_total
            block.amount_total = untaxed + tax_total

    def write(self, vals):
        res = super().write(vals)
        # Findings 2/5: the vendor and the dates are signed off at approval but
        # are NOT part of the amount fingerprint, so changing them AFTER approval
        # must void it — otherwise a post-approval vendor swap would bill a payee
        # (or an accounting period) the approver never signed off. Mirrors how
        # editing an amount already invalidates via the approval mixin. The
        # internal billing / state-sync writes only touch state/bill_id, so they
        # never trip this; the skip context keeps ORM/idempotent writes quiet.
        if ({'vendor_id', 'date', 'bill_date'} & set(vals)
                and not self.env.context.get('way4tech_skip_approval_invalidation')):
            self.env['way4tech.manpower.approval.request']._invalidate_for(self)
        return res

    # ── Actions ─────────────────────────────────────────────────────────────
    def action_create_bill(self):
        """Create ONE vendor bill (draft) carrying every line in this block,
        billed to the block's single vendor. Mirrors the per-line
        project.expense.action_create_bill accounting for each line."""
        self.ensure_one()
        if self.bill_id:
            raise UserError(_(
                'This block already produced bill "%(bill)s".\n\n'
                'Correct that bill in Accounting instead. To bill something '
                'else, use a fresh block; to release this one, cancel or delete '
                'the linked bill.'
            ) % {'bill': self.bill_id.display_name})
        if not self.line_ids:
            raise UserError(_(
                'This bill block has no lines yet. Add at least one line before '
                'creating the bill.'
            ))
        if not self.vendor_id:
            raise UserError(_('Set a Vendor before creating the bill.'))
        contract = self.contract_id
        # Item 7: ensure this block's vendor posts its payable to an ACTIVE
        # account even if the company's default payable has been archived, so
        # the combined bill can be posted without an "account is archived" error.
        contract._way4tech_ensure_active_payable(self.vendor_id)
        # Same monthly signature-approval gate as every other document-creating
        # action on the contract; burned on success below.
        contract._require_month_approval(record=self)
        settings = self.env['way4tech.payroll.settings'].get_for_company(
            contract.company_id.id)

        # Direct-Cost invoice-first rule (mirror of the per-line check): if any
        # line in this block is Direct Cost, the contract must already carry a
        # customer invoice (the bill's Payment Reference is composed from it).
        any_direct = any(
            (not l.category_id) or l.category_id.expense_type == 'direct'
            for l in self.line_ids
        )
        if any_direct and not contract.invoice_ids:
            raise ValidationError(_(
                'Cannot create this Direct Cost bill — the contract has no '
                'customer invoice yet. Create the customer invoice first '
                '(Project Income); Operating Exp lines are exempt.'
            ))

        distribution = contract._resolve_analytic_distribution(settings)
        source_lines = self.line_ids.sorted(lambda l: l.id)
        bill_lines = []
        for line in source_lines:
            account = line.account_id
            if not account and line.category_id:
                account = line.category_id.resolve_expense_account(
                    contract.company_id, raise_if_missing=True)
            if not account:
                raise UserError(_(
                    'Line "%s" has no expense account. Set it on the line or '
                    'configure the category account in Payroll & Accounting '
                    'Setup.'
                ) % (line.description or ''))
            if line.price:
                # Use the line's real quantity (NOT `or 1.0`): the block preview
                # totals from line.amount (= qty x price), so a qty=0 line must
                # bill 0 too, not silently post 1 x price.
                bl_qty, bl_price = line.quantity, line.price
            else:
                bl_qty, bl_price = 1.0, line.amount
            _pname, _pdesc = (line.product_id.name or ''), (line.description or '')
            bl_name = ('%s\n%s' % (_pname, _pdesc)) if (_pname and _pdesc) \
                else (_pname or _pdesc)
            line_vals = {
                'name': bl_name,
                'quantity': bl_qty,
                'price_unit': bl_price,
                'account_id': account.id,
            }
            tax = self._way4tech_line_input_vat(line, settings)
            _is_direct = (not line.category_id) or \
                line.category_id.expense_type == 'direct'
            if tax:
                line_vals['tax_ids'] = [(6, 0, [tax.id])]
            elif _is_direct:
                raise UserError(_(
                    'No Input VAT tax configured for category "%s" (Direct '
                    'Cost). Configure it in Payroll & Accounting Setup → '
                    'Manpower Contracts → Expense Category map.'
                ) % (line.category_id.name if line.category_id else '(none)'))
            if distribution:
                line_vals['analytic_distribution'] = distribution
            bill_lines.append((0, 0, line_vals))

        journal = settings.project_expense_journal_id or self.env[
            'account.journal'].search([
                ('type', '=', 'purchase'),
                ('company_id', '=', contract.company_id.id),
            ], limit=1)

        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.vendor_id.id,
            'invoice_date': self.bill_date or self.date,
            'date': self.date,
            'company_id': contract.company_id.id,
            'ref': '%s / %s' % (contract.name, _('Bill Block')),
            'invoice_line_ids': bill_lines,
            'payment_reference': contract._compose_reference_string(
                invoice=contract.invoice_ids[:1]),
        }
        if journal:
            bill_vals['journal_id'] = journal.id
        if contract.way4tech_project_id:
            bill_vals['way4tech_project_id'] = contract.way4tech_project_id.id
        if contract.way4tech_category_id:
            bill_vals['way4tech_category_id'] = contract.way4tech_category_id.id
        else:
            category = self.env.ref(
                'way4tech_logistics.category_others', raise_if_not_found=False)
            if category:
                bill_vals['way4tech_category_id'] = category.id
        all_tags = contract.tag_ids | self.line_ids.mapped('tag_ids')
        if all_tags:
            bill_vals['way4tech_tag_ids'] = [(6, 0, all_tags.ids)]

        bill = self.env['account.move'].create(bill_vals)
        contract._apply_ksa_account_overrides(bill)

        # Pin each expense line to the exact bill line it produced (so the
        # existing per-line sync-back reads the right subtotal on this
        # multi-line bill) and flip it to billed. vendor_id is aligned to the
        # block vendor so the stored line stays consistent with its bill.
        created_lines = bill.invoice_line_ids
        for source, created in zip(source_lines, created_lines):
            source.write({
                'bill_id': bill.id,
                'bill_line_id': created.id,
                'vendor_id': self.vendor_id.id,
                'state': 'billed',
            })
        self.write({'bill_id': bill.id, 'state': 'billed'})
        contract._consume_approval(self)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_bill(self):
        self.ensure_one()
        if not self.bill_id:
            raise UserError(_('This block has not produced a bill yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'res_id': self.bill_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def unlink(self):
        """Mirror the line/invoice-block guard: a block whose bill is POSTED
        cannot be deleted. Draft / cancelled bills allow it, and the expense
        lines simply return to the unassigned pool (bill_block_id set null)."""
        for block in self:
            move = block.bill_id
            if move and move.state == 'posted':
                raise UserError(_(
                    'Cannot delete bill block "%s" — its bill "%s" is POSTED. '
                    'Reset the bill to draft or cancel it from the Accounting '
                    'menu first.'
                ) % (block.name or '', move.display_name))
        return super().unlink()
