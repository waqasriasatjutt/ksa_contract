# -*- coding: utf-8 -*-
"""Project Income line (P4) — one row per invoice-worthy revenue item on
a Manpower Contract. Each line has its own accounting date, description,
sale account, quantity/price, and a per-line "Create Invoice" button that
mints an ``account.move`` inheriting the contract's analytic distribution,
project, category, tags, and PRO reference.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class Way4TechManpowerContractIncomeLine(models.Model):
    _name = "way4tech.manpower.contract.income.line"
    _description = "Manpower Contract — Project Income Line"
    _inherit = ['way4tech.manpower.approval.mixin']
    # _order does NOT include accounting_date: sorting by an editable date
    # field means every date pick triggers a row-position resort in the
    # inline editable list, which re-renders the row and re-focuses the
    # picker → infinite reopen loop.
    #
    # CR3-FINAL round 2, polish 12: sequence-then-id ASCENDING, so rows keep
    # the order they were typed in. Under "id desc" an invoice block billed
    # its lines newest-first and the printed invoice came out reversed.
    _order = "sequence, id"

    sequence = fields.Integer(default=10, help="Display / billing order.")

    contract_id = fields.Many2one(
        "way4tech.manpower.contract", required=True, ondelete="cascade",
    )
    # CR3-FINAL P6: when set, this row is one line of a multi-line invoice
    # block rather than a standalone single-line invoice. ondelete='set null'
    # — deleting a draft block must never destroy the operator's typed income
    # rows; they simply return to the unassigned pool.
    invoice_block_id = fields.Many2one(
        "way4tech.manpower.invoice.block",
        string="Invoice Block",
        ondelete="set null", index=True, copy=False,
        help="The multi-line invoice block this row belongs to. Rows sharing "
             "a block are billed together on ONE customer invoice.",
    )
    company_id = fields.Many2one(related="contract_id.company_id", store=True, readonly=True)
    currency_id = fields.Many2one(related="contract_id.currency_id", store=True, readonly=True)

    accounting_date = fields.Date(string="Accounting Date", required=True, default=fields.Date.context_today)
    # store=False on the Char compute so setting accounting_date in an inline
    # editable list does NOT write a DB column on every pick — the extra write
    # triggers a row re-render that re-focuses the date input and re-opens
    # the calendar (picker-loop bug users saw on 2026-07-15).
    inv_month = fields.Char(
        string="Inv Month (Auto)",
        compute="_compute_inv_month",
    )
    invoice_date = fields.Date(string="Invoice Date", default=fields.Date.context_today)
    description = fields.Char(string="Description", required=True)
    tag_ids = fields.Many2many(
        "way4tech.tag",
        "way4tech_income_line_tag_rel",
        "line_id", "tag_id",
        string="Contract Tags",
    )
    # CR3-FINAL round 3, item 10: stored compute with readonly=False instead of
    # an onchange. Inside an invoice block the row is created with contract_id
    # arriving from context, so the old @api.onchange('contract_id') never
    # fired and the Sale Account came up empty — the user had to look up
    # 410001 by hand on every line. A compute fills it however the row is
    # created (UI, block, import, code) and still lets them override.
    sale_account_id = fields.Many2one(
        "account.account", string="Sale Account", check_company=True,
        compute="_compute_sale_account_id", store=True, readonly=False,
    )

    @api.depends("contract_id")
    def _compute_sale_account_id(self):
        for line in self:
            if line.sale_account_id:
                continue          # never overwrite an explicit choice
            contract = line.contract_id
            if not contract:
                line.sale_account_id = False
                continue
            settings = self.env["way4tech.payroll.settings"].get_for_company(
                contract.company_id.id,
            )
            line.sale_account_id = settings.manpower_income_account_id or False
    # CR3-FINAL round 4, item 8: explicit 2-decimal display. Without digits a
    # Float renders at the generic precision, so the block grid showed
    # 2.000000 / 1,000.000000.
    quantity = fields.Float(string="Quantity", default=1.0, digits=(16, 2))
    price = fields.Float(string="Price", digits=(16, 2))
    amount = fields.Monetary(
        string="Amount", compute="_compute_amount", store=True, currency_field="currency_id",
    )
    invoice_id = fields.Many2one("account.move", string="Invoice", readonly=True, copy=False)
    # CR2 G4 amendment A: pin the specific invoice_line the create action
    # minted, so _sync_amount_from_move reads price_subtotal from that
    # exact line — never the whole move.amount_untaxed (which would treat
    # any extra discount/adjustment row on the invoice as "our" amount and
    # silently corrupt price on the source-line).
    invoice_line_id = fields.Many2one(
        'account.move.line',
        string='Invoice Line',
        readonly=True, copy=False, ondelete='set null',
        help='CR2 G4: the specific account.move.line minted by Create Invoice '
             'on this row. Sync back-reads price_subtotal from this line, not '
             'the whole invoice, so multi-line invoices stay consistent.',
    )
    state = fields.Selection(
        [("draft", "Draft"), ("invoiced", "Invoiced")],
        default="draft", readonly=True, copy=False,
    )

    @api.depends("accounting_date")
    def _compute_inv_month(self):
        for line in self:
            line.inv_month = line.accounting_date.strftime("%m/%Y") if line.accounting_date else False

    @api.depends("quantity", "price")
    def _compute_amount(self):
        for line in self:
            line.amount = (line.quantity or 0.0) * (line.price or 0.0)

    # (the old @api.onchange('contract_id') is now _compute_sale_account_id
    #  above — an onchange did not fire for rows created inside a block)

    def action_create_invoice(self):
        """Mint a customer invoice for this single income line. Mirrors the
        contract-level ``action_create_invoice`` (same analytic, project,
        category, tags, PRO ref) but scoped to THIS line's account + amount.

        CR3-FINAL P6: kept for continuity with rows created before invoice
        blocks existed. A row that belongs to a block must be billed through
        the block so all its sibling lines land on the same invoice.
        """
        for line in self:
            if line.invoice_id:
                raise UserError(_("This income line has already been invoiced."))
            if line.invoice_block_id:
                raise UserError(_(
                    'This row belongs to invoice block "%s". Use that block\'s '
                    '"Create Invoice" button so every line in the block is '
                    'billed on the same invoice.'
                ) % (line.invoice_block_id.name or ''))
            # CR2 G5 (19.0.2.9.0): monthly signature-approval gate.
            line.contract_id._require_month_approval(record=line)
            contract = line.contract_id
            settings = self.env["way4tech.payroll.settings"].get_for_company(contract.company_id.id)
            distribution = contract._resolve_analytic_distribution(settings)
            sale_account = line.sale_account_id or settings.manpower_income_account_id
            if not sale_account:
                raise UserError(_(
                    "No sale account configured. Set one on the income line OR set "
                    "'Manpower Income Account' in Payroll & Accounting Setup."
                ))
            vat_tax = self.env["account.tax"].search([
                ("type_tax_use", "=", "sale"),
                ("amount_type", "=", "percent"),
                ("amount", "=", 15.0),
                ("company_id", "=", contract.company_id.id),
            ], limit=1)
            if not vat_tax:
                raise UserError(_("No 15% sales tax configured for this company."))

            line_vals = {
                "name": line.description,
                "quantity": line.quantity or 1.0,
                "price_unit": line.price or 0.0,
                "account_id": sale_account.id,
                "tax_ids": [(6, 0, [vat_tax.id])],
            }
            if distribution:
                line_vals["analytic_distribution"] = distribution

            move_vals = {
                "move_type": "out_invoice",
                "partner_id": contract.client_id.id,
                "company_id": contract.company_id.id,
                "invoice_date": line.invoice_date or line.accounting_date,
                "date": line.accounting_date,
                "invoice_line_ids": [(0, 0, line_vals)],
            }
            if settings.manpower_journal_id:
                move_vals["journal_id"] = settings.manpower_journal_id.id
            if contract.way4tech_project_id:
                move_vals["way4tech_project_id"] = contract.way4tech_project_id.id
            if contract.way4tech_category_id:
                move_vals["way4tech_category_id"] = contract.way4tech_category_id.id
            all_tags = (contract.tag_ids | line.tag_ids)
            if all_tags:
                move_vals["way4tech_tag_ids"] = [(6, 0, all_tags.ids)]

            invoice = self.env["account.move"].create(move_vals)
            invoice.ref = contract._compose_reference_string(invoice=invoice)
            contract._apply_ksa_account_overrides(invoice)
            # CR2 G4: pin the specific invoice_line for per-line sync-back.
            line.write({
                "invoice_id": invoice.id,
                "invoice_line_id": invoice.invoice_line_ids[:1].id or False,
                "state": "invoiced",
            })
            contract.invoice_ids = [(4, invoice.id)]
            contract._consume_approval(line)
        return {
            "type": "ir.actions.act_window",
            "name": _("Invoice"),
            "res_model": "account.move",
            "res_id": self[:1].invoice_id.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_invoice(self):
        """CR2 G4: per-row 'View Invoice' button — parity with expense/
        commission tabs that already have action_view_bill."""
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_('No invoice linked to this income line yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'res_id': self.invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _sync_amount_from_move(self, move):
        """CR2 G4: pull the current price_subtotal of the linked invoice
        LINE (not the whole move) back into this income line. Skip
        silently if invoice_line_id is not pinned (legacy pre-G4 row) —
        never guess amount from move.amount_untaxed on such rows
        (skeptic amendment A: prevents multi-line data corruption)."""
        self.ensure_one()
        if move.move_type not in ('out_invoice', 'out_refund'):
            return
        if not self.invoice_line_id:
            # Legacy row without pinned line — don't corrupt.
            return
        line_amount = self.invoice_line_id.price_subtotal or 0.0
        qty = self.quantity or 1.0
        new_price = line_amount / qty
        if new_price != self.price:
            self.with_context(way4tech_skip_move_sync=True).write({'price': new_price})

    def unlink(self):
        """CR2 G4 item 4/5: block deletion while linked invoice is POSTED.
        Draft or cancelled invoices allow deletion (skeptic amendment E:
        the 'must cancel first for even drafts' UX was too onerous)."""
        for line in self:
            move = line.invoice_id
            if move and move.state == 'posted':
                raise UserError(_(
                    'Cannot delete this Project Income line — the linked '
                    'invoice "%s" is POSTED. Reset the invoice to draft or '
                    'cancel it from the Accounting menu first, then retry.'
                ) % move.display_name)
        return super().unlink()
