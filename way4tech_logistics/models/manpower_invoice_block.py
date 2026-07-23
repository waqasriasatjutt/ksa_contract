# -*- coding: utf-8 -*-
"""CR3-FINAL P6 — Multi-line invoice built directly from the contract.

Before this, every Project Income row minted its own single-line invoice, so
building a 3-line invoice meant creating one, opening the posted document and
hand-adding the other two lines. That is exactly the screen-to-screen travel
the client asked us to remove.

An *invoice block* is a grouped line-table representing ONE future invoice:

    Create New Invoice  →  a new block opens
    add N income lines inside it
    the block's Create Invoice  →  ONE account.move carrying all N lines
    the block locks and shows View Invoice
    Create New Invoice again    →  another block  →  another invoice

A contract-month can therefore hold several invoices. The accounting setup is
unchanged from the single-line path — same analytic distribution, Entry
Category, Project, Tags, PRO reference, receivable override and 15% Output
VAT — so nothing about how these documents post to the GL changes.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class Way4TechManpowerInvoiceBlock(models.Model):
    _name = 'way4tech.manpower.invoice.block'
    _description = 'Manpower Contract — Invoice Block (multi-line invoice)'
    _inherit = ['way4tech.manpower.approval.mixin']
    # Newest block first, and never order by an editable date field — that is
    # the date-picker re-focus loop documented across CR2 G1 / v11.0.
    _order = 'id desc'

    name = fields.Char(
        string='Invoice Block', compute='_compute_name', store=True,
        help='Auto-generated label. Shows the created invoice number once the '
             'block has been invoiced.',
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
    # Block-level header dates — applied to the single invoice this block
    # produces. Individual income lines keep their own dates for reporting.
    accounting_date = fields.Date(
        string='Accounting Date', required=True,
        default=fields.Date.context_today,
        help='Posting date (account.move.date) of the invoice this block creates.',
    )
    invoice_date = fields.Date(
        string='Invoice Date', required=True,
        default=fields.Date.context_today,
        help='Document date (account.move.invoice_date) of the invoice this '
             'block creates.',
    )
    line_ids = fields.One2many(
        'way4tech.manpower.contract.income.line', 'invoice_block_id',
        string='Invoice Lines',
        help='Every row here becomes one line on the SAME customer invoice.',
    )
    line_count = fields.Integer(
        string='Lines', compute='_compute_totals', store=True,
    )
    amount_untaxed = fields.Monetary(
        string='Untaxed Total', compute='_compute_totals', store=True,
        currency_field='currency_id',
    )
    invoice_id = fields.Many2one(
        'account.move', string='Invoice', readonly=True, copy=False,
    )
    # CR3-FINAL round 2, new item 1: three states, not two.
    # A block whose invoice was reset to draft used to fall back to 'draft',
    # which showed a Create Invoice button that could only ever raise "this
    # block has already produced invoice X" — visible, dead, and leaving the
    # draft invoice unattended. 'invoice_draft' is that middle ground: still
    # linked, still showing View Invoice, waiting to be corrected and
    # re-confirmed. The block is only freed back to 'draft' when the linked
    # invoice is cancelled or deleted.
    state = fields.Selection(
        [('draft', 'Draft'),
         ('invoice_draft', 'Invoice in Draft'),
         ('invoiced', 'Invoiced')],
        default='draft', readonly=True, copy=False,
    )

    # ── CR3-FINAL round 2, new item 2: show the real payable figure ───────
    # The block only ever showed the untaxed total, so a block reading
    # "5,000.00" produced a 5,750.00 invoice and the user never saw the gross
    # until after creation.
    amount_tax = fields.Monetary(
        string='VAT', compute='_compute_totals', store=True,
        currency_field='currency_id',
        help='15% Output VAT that will be applied when this block is invoiced.',
    )
    amount_total = fields.Monetary(
        string='Total', compute='_compute_totals', store=True,
        currency_field='currency_id',
        help='Gross total including VAT — the amount the invoice will carry.',
    )
    note = fields.Char(
        string='Reference / Note',
        help='Optional free text. Appended to the invoice reference.',
    )

    @api.depends('invoice_id', 'invoice_id.name', 'accounting_date', 'state')
    def _compute_name(self):
        for block in self:
            if block.invoice_id and block.invoice_id.name:
                block.name = block.invoice_id.name
            elif block.accounting_date:
                block.name = _('Draft Invoice — %s') % (
                    block.accounting_date.strftime('%d/%m/%Y')
                )
            else:
                block.name = _('Draft Invoice')

    def _get_sale_vat_tax(self):
        """The 15% Output VAT applied to every line this block invoices."""
        self.ensure_one()
        company = self.contract_id.company_id or self.env.company
        return self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('amount_type', '=', 'percent'),
            ('amount', '=', 15.0),
            ('company_id', '=', company.id),
        ], limit=1)

    @api.depends('line_ids', 'line_ids.amount', 'contract_id.company_id')
    def _compute_totals(self):
        for block in self:
            block.line_count = len(block.line_ids)
            untaxed = sum(block.line_ids.mapped('amount'))
            block.amount_untaxed = untaxed
            # Compute VAT through the tax record rather than hard-coding 15%,
            # so the preview matches whatever the invoice will actually post.
            tax = block._get_sale_vat_tax()
            if tax and untaxed:
                block.amount_tax = tax.amount / 100.0 * untaxed
            else:
                block.amount_tax = 0.0
            block.amount_total = untaxed + block.amount_tax

    # ── Actions ───────────────────────────────────────────────────────────
    def action_create_invoice(self):
        """Create ONE customer invoice carrying every line in this block."""
        self.ensure_one()
        # CR3-FINAL round 2, new item 1: a cancelled invoice no longer blocks
        # the block — it is released below by _way4tech_sync_source_states, so
        # reaching here with a live invoice_id genuinely means one exists.
        if self.invoice_id:
            raise UserError(_(
                'This block is already linked to invoice "%(inv)s" (%(state)s).\n\n'
                'Correct and re-confirm that invoice instead — the block will '
                'return to Invoiced. To bill something else, use "Create New '
                'Invoice" for a fresh block. To release this block, cancel or '
                'delete the linked invoice.'
            ) % {
                'inv': self.invoice_id.display_name,
                'state': dict(
                    self.invoice_id._fields['state'].selection,
                ).get(self.invoice_id.state, self.invoice_id.state),
            })
        if not self.line_ids:
            raise UserError(_(
                'This invoice block has no lines yet. Add at least one line '
                'before creating the invoice.'
            ))
        contract = self.contract_id
        # CR2 G5 monthly signature-approval gate — same rule as every other
        # document-creating action on the contract.
        # CR3-FINAL Part A: approval is matched to THIS block, and burned below.
        contract._require_month_approval(record=self)

        settings = self.env['way4tech.payroll.settings'].get_for_company(
            contract.company_id.id,
        )
        distribution = contract._resolve_analytic_distribution(settings)
        vat_tax = self.env['account.tax'].search([
            ('type_tax_use', '=', 'sale'),
            ('amount_type', '=', 'percent'),
            ('amount', '=', 15.0),
            ('company_id', '=', contract.company_id.id),
        ], limit=1)
        if not vat_tax:
            raise UserError(_('No 15% sales tax configured for this company.'))

        # CR3-FINAL round 2, polish 12: bill lines in ENTRY order. The income
        # line model sorts newest-first, so iterating the o2m raw printed the
        # invoice in reverse (Sweeper → electrician → plumber came out
        # backwards). sequence-then-id is the order shown in the block grid.
        source_lines = self.line_ids.sorted(lambda l: (l.sequence, l.id))
        invoice_lines = []
        for line in source_lines:
            sale_account = line.sale_account_id or settings.manpower_income_account_id
            if not sale_account:
                raise UserError(_(
                    'Line "%s" has no Sale Account, and no Manpower Income '
                    'Account is set in Payroll & Accounting Setup.'
                ) % (line.description or ''))
            line_vals = {
                'name': line.description,
                'quantity': line.quantity or 1.0,
                'price_unit': line.price or 0.0,
                'account_id': sale_account.id,
                'tax_ids': [(6, 0, [vat_tax.id])],
            }
            if distribution:
                line_vals['analytic_distribution'] = distribution
            invoice_lines.append((0, 0, line_vals))

        move_vals = {
            'move_type': 'out_invoice',
            'partner_id': contract.client_id.id,
            'company_id': contract.company_id.id,
            'invoice_date': self.invoice_date,
            'date': self.accounting_date,
            'invoice_line_ids': invoice_lines,
        }
        if settings.manpower_journal_id:
            move_vals['journal_id'] = settings.manpower_journal_id.id
        if contract.way4tech_project_id:
            move_vals['way4tech_project_id'] = contract.way4tech_project_id.id
        if contract.way4tech_category_id:
            move_vals['way4tech_category_id'] = contract.way4tech_category_id.id
        else:
            category = self.env.ref(
                'way4tech_logistics.category_manpower_revenue',
                raise_if_not_found=False,
            )
            if category:
                move_vals['way4tech_category_id'] = category.id
        if contract.po_id:
            move_vals['way4tech_po_id'] = contract.po_id.id
        all_tags = contract.tag_ids | self.line_ids.mapped('tag_ids')
        if all_tags:
            move_vals['way4tech_tag_ids'] = [(6, 0, all_tags.ids)]

        invoice = self.env['account.move'].create(move_vals)
        # CR3-FINAL round 4, item 6: the block Note is no longer appended to
        # the Customer Reference. It never printed on the PDF, so the customer
        # never saw it, and free text muddied the PRO/YYYY/MM/xxxx reference we
        # filter and match on. Customer Reference now carries only the clean
        # composed reference.
        invoice.ref = contract._compose_reference_string(invoice=invoice)
        contract._apply_ksa_account_overrides(invoice)

        # Pin each source line to the exact invoice line it produced, so the
        # existing CR2 G4 per-line sync-back keeps reading the right subtotal
        # on a MULTI-line invoice (reading move.amount_untaxed here would
        # attribute the whole invoice to every line).
        created_lines = invoice.invoice_line_ids
        for source, created in zip(self.line_ids, created_lines):
            source.write({
                'invoice_id': invoice.id,
                'invoice_line_id': created.id,
                'state': 'invoiced',
            })
        self.write({'invoice_id': invoice.id, 'state': 'invoiced'})
        contract.invoice_ids = [(4, invoice.id)]
        # Part A: the approval is spent. It unlocks nothing else, ever.
        contract._consume_approval(self)
        # Part A point 11: create AND post in one step, from the contract. The
        # approval WAS the review; routing the user to the invoice form to
        # press Confirm would let them edit after sign-off. If posting fails
        # validation, roll the whole thing back rather than leave a half-made
        # document behind.
        try:
            invoice.action_post()
        except Exception as exc:            # noqa: BLE001
            raise UserError(_(
                'The invoice could not be posted, so nothing was created.\n\n'
                '%s\n\nFix the underlying data (partner, accounts, taxes, '
                'analytic) and try again.'
            ) % exc) from exc
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'res_id': invoice.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_('This block has not been invoiced yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def unlink(self):
        """Mirror the line-level guard: a block whose invoice is POSTED can
        not be deleted. Draft / cancelled invoices allow it."""
        for block in self:
            move = block.invoice_id
            if move and move.state == 'posted':
                raise UserError(_(
                    'Cannot delete invoice block "%s" — its invoice "%s" is '
                    'POSTED. Reset the invoice to draft or cancel it from the '
                    'Accounting menu first.'
                ) % (block.name or '', move.display_name))
        return super().unlink()
