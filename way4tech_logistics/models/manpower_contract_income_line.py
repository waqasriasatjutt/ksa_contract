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
    _order = "accounting_date desc, id desc"

    contract_id = fields.Many2one(
        "way4tech.manpower.contract", required=True, ondelete="cascade",
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
    sale_account_id = fields.Many2one(
        "account.account", string="Sale Account", check_company=True,
    )
    quantity = fields.Float(string="Quantity", default=1.0)
    price = fields.Float(string="Price")
    amount = fields.Monetary(
        string="Amount", compute="_compute_amount", store=True, currency_field="currency_id",
    )
    invoice_id = fields.Many2one("account.move", string="Invoice", readonly=True, copy=False)
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

    @api.onchange("contract_id")
    def _onchange_contract_default_sale_account(self):
        if not self.sale_account_id and self.contract_id:
            settings = self.env["way4tech.payroll.settings"].get_for_company(
                self.contract_id.company_id.id,
            )
            self.sale_account_id = settings.manpower_income_account_id

    def action_create_invoice(self):
        """Mint a customer invoice for this single income line. Mirrors the
        contract-level ``action_create_invoice`` (same analytic, project,
        category, tags, PRO ref) but scoped to THIS line's account + amount."""
        for line in self:
            if line.invoice_id:
                raise UserError(_("This income line has already been invoiced."))
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
            line.write({"invoice_id": invoice.id, "state": "invoiced"})
            contract.invoice_ids = [(4, invoice.id)]
        return {
            "type": "ir.actions.act_window",
            "name": _("Invoice"),
            "res_model": "account.move",
            "res_id": self[:1].invoice_id.id,
            "view_mode": "form",
            "target": "current",
        }
