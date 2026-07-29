# -*- coding: utf-8 -*-
"""CR6 item 1 — Timesheet Invoice Block: bill several timesheet lines on ONE
customer invoice, exactly like the Project Income invoice block does for income
lines.

This is ADDITIVE. The existing flat Timesheets list and its per-line Create
Invoice button are untouched — a timesheet that only needs its own invoice keeps
working as before. A block is the multi-line path: open a block, add the
timesheet lines that belong on the same invoice, click Create Invoice, and every
line lands on ONE account.move with the same analytic distribution, income
account, 15% Output VAT, project, category and PRO reference the single-line
path already applies. So nothing about how these documents post to the GL
changes.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class Way4TechManpowerTimesheetBlock(models.Model):
    _name = 'way4tech.manpower.timesheet.block'
    _description = 'Manpower Contract — Timesheet Invoice Block (multi-line invoice)'
    _inherit = ['way4tech.manpower.approval.mixin',
                'way4tech.manpower.docline.mixin']
    # Download-only (its invoice PDF) like the income invoice block — user
    # attachments live on the timesheet lines, so no attach dialog here.
    # Newest first; never order by an editable date field (date-picker loop).
    _order = 'id desc'

    name = fields.Char(
        string='Timesheet Invoice', compute='_compute_name', store=True,
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
    accounting_date = fields.Date(
        string='Accounting Date', required=True,
        default=lambda self: self._way4tech_default_period_date(),
        help='Posting date (account.move.date) of the invoice this block creates.',
    )
    invoice_date = fields.Date(
        string='Invoice Date', required=True,
        default=fields.Date.context_today,
        help='Document date (account.move.invoice_date) of the invoice this '
             'block creates.',
    )
    line_ids = fields.One2many(
        'way4tech.manpower.timesheet', 'timesheet_block_id',
        string='Timesheet Lines',
        help='Every timesheet row here becomes one line on the SAME customer '
             'invoice.',
    )
    line_count = fields.Integer(
        string='Lines', compute='_compute_totals', store=True,
    )
    amount_untaxed = fields.Monetary(
        string='Untaxed Total', compute='_compute_totals', store=True,
        currency_field='currency_id',
    )
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
    invoice_id = fields.Many2one(
        'account.move', string='Invoice', readonly=True, copy=False,
    )
    # Same three states as the income invoice block (a reset-to-draft invoice
    # keeps the block linked as 'invoice_draft', freed only when the invoice is
    # cancelled/deleted).
    state = fields.Selection(
        [('draft', 'Draft'),
         ('invoice_draft', 'Invoice in Draft'),
         ('invoiced', 'Invoiced')],
        default='draft', readonly=True, copy=False,
    )

    @api.depends('invoice_id', 'invoice_id.name', 'accounting_date', 'state')
    def _compute_name(self):
        for block in self:
            if block.invoice_id and block.invoice_id.name:
                block.name = block.invoice_id.name
            elif block.accounting_date:
                block.name = _('Draft Timesheet Invoice — %s') % (
                    block.accounting_date.strftime('%d/%m/%Y')
                )
            else:
                block.name = _('Draft Timesheet Invoice')

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
            tax = block._get_sale_vat_tax()
            if tax and untaxed:
                block.amount_tax = tax.amount / 100.0 * untaxed
            else:
                block.amount_tax = 0.0
            block.amount_total = untaxed + block.amount_tax

    # ── Actions ───────────────────────────────────────────────────────────
    def action_create_invoice(self):
        """Create ONE customer invoice carrying every timesheet line in this
        block. Mirrors the income invoice block: same approval gate, analytic
        distribution, income account, 15% Output VAT, project / category / tags
        / PRO reference, then post — all rolled back together if posting fails."""
        self.ensure_one()
        if self.invoice_id:
            raise UserError(_(
                'This block is already linked to invoice "%(inv)s" (%(state)s).\n\n'
                'Correct and re-confirm that invoice instead — the block will '
                'return to Invoiced. To bill something else, use a fresh block.'
            ) % {
                'inv': self.invoice_id.display_name,
                'state': dict(
                    self.invoice_id._fields['state'].selection,
                ).get(self.invoice_id.state, self.invoice_id.state),
            })
        if not self.line_ids:
            raise UserError(_(
                'This timesheet invoice block has no lines yet. Add at least one '
                'timesheet line before creating the invoice.'
            ))
        contract = self.contract_id
        # Same monthly signature-approval gate as every other document action,
        # matched to THIS block and burned below.
        contract._require_month_approval(record=self)

        settings = self.env['way4tech.payroll.settings'].get_for_company(
            contract.company_id.id,
        )
        distribution = contract._resolve_analytic_distribution(settings)
        sale_account = settings.manpower_income_account_id
        if not sale_account:
            raise UserError(_(
                'No Manpower Income Account configured in Payroll & Accounting '
                'Setup.'
            ))
        vat_tax = self._get_sale_vat_tax()
        if not vat_tax:
            raise UserError(_('No 15% sales tax configured for this company.'))

        invoice_lines = []
        for line in self.line_ids:
            # Same per-line figures the single-line timesheet invoice uses:
            # Quantity = Hours, Price = Rate; fall back to (1 x amount) on
            # legacy rows with no rate so they are never zero-priced.
            if line.rate:
                inv_qty = line.hours or 0.0
                inv_price = line.rate
            else:
                inv_qty = 1.0
                inv_price = line.amount or 0.0
            desc = line.description or _('Timesheet %s') % (
                line.date or line.start_date or '')
            line_vals = {
                'name': desc,
                'quantity': inv_qty,
                'price_unit': inv_price,
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
        all_tags = contract.tag_ids | self.line_ids.mapped('tag_ids')
        if all_tags:
            move_vals['way4tech_tag_ids'] = [(6, 0, all_tags.ids)]

        invoice = self.env['account.move'].create(move_vals)
        invoice.ref = contract._compose_reference_string(invoice=invoice)
        contract._apply_ksa_account_overrides(invoice)

        # Pin each source timesheet to the exact invoice line it produced, so
        # the CR2 G4 per-line amount sync-back keeps reading the right subtotal
        # on a multi-line invoice.
        created_lines = invoice.invoice_line_ids
        for source, created in zip(self.line_ids, created_lines):
            source.write({
                'invoice_id': invoice.id,
                'invoice_line_id': created.id,
                'state': 'invoiced',
            })
        self.write({'invoice_id': invoice.id, 'state': 'invoiced'})
        contract.invoice_ids = [(4, invoice.id)]
        contract._consume_approval(self)
        # Create AND post in one step, like the income block — the approval was
        # the review. Roll the whole thing back if posting fails.
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
        """A block whose invoice is POSTED cannot be deleted (mirror the income
        block guard). Draft / cancelled invoices allow it."""
        for block in self:
            move = block.invoice_id
            if move and move.state == 'posted':
                raise UserError(_(
                    'Cannot delete timesheet invoice block "%s" — its invoice '
                    '"%s" is POSTED. Reset the invoice to draft or cancel it '
                    'from the Accounting menu first.'
                ) % (block.name or '', move.display_name))
        return super().unlink()
