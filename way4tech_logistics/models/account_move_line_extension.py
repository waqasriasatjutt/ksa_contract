# -*- coding: utf-8 -*-
"""Propagate the invoice-header dimensions onto the journal lines.

The three custom dimensions — Project, Tags and Entry Category ("Other
Category") — live only on ``account.move`` (the invoice header). Financial
reports (Balance Sheet, Partner Ledger, P&L) and journal-entry drill-downs read
``account.move.line``, so those fields were invisible/unfilterable there.

We mirror them onto the journal line and keep them in sync with the header:
  * **Project / Entry Category** — stored ``related`` fields (simplest).
  * **Tags** — a stored *computed* Many2many with its own relation table. A
    stored *related* m2m cannot be created by Odoo (it can't derive/keep a
    relation name → ``AttributeError: 'NoneType' … isidentifier``), so we use a
    plain ``@api.depends`` compute instead — same effect.

All three are stored + indexed, so Odoo back-fills every existing line on
upgrade and keeps them in sync on any header change (draft edit, reset-to-draft
+ re-post) — no ``_post()``/``write()`` override and no migration script needed.
They become filterable / group-able everywhere journal lines are shown.
(The client rejected Analytic Accounts — they want these exact custom fields.)
"""
from odoo import api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    # readonly=False makes these editable ON THE LINE (incl. bulk multi-edit in
    # the ledger/journal-items list). A stored related m2o with readonly=False
    # writes straight back to the header (move_id.*); the m2m uses an explicit
    # inverse. Because the dimension is entry-level, editing any line's value
    # sets it for the whole journal entry (all its lines stay in sync).
    way4tech_project_id = fields.Many2one(
        related="move_id.way4tech_project_id",
        store=True,
        index=True,
        readonly=False,
        string="Project",
    )
    way4tech_category_id = fields.Many2one(
        related="move_id.way4tech_category_id",
        store=True,
        index=True,
        readonly=False,
        string="Entry Category",
    )
    way4tech_tag_ids = fields.Many2many(
        comodel_name="way4tech.tag",
        relation="way4tech_move_line_tag_rel",
        column1="line_id",
        column2="tag_id",
        string="Contract Tags",
        compute="_compute_way4tech_line_tags",
        inverse="_inverse_way4tech_line_tags",
        store=True,
        readonly=False,
    )
    # Alzain Fix 2 (2026-08): back-reference from an invoice line to the
    # Manpower Invoice Block income line that owns it. Set only on lines the
    # block manages. Needed for the two-way DRAFT sync: after an income row is
    # removed from the wizard its forward pin (income_line.invoice_line_id) is
    # gone, so this back-pin is the only way to know which invoice line to
    # delete — and, the other way, which invoice lines already have a wizard
    # row (so a line added in Accounting spawns exactly one new row).
    # ondelete='set null' so deleting the wizard row never cascades to the
    # invoice line; copy=False so a duplicated invoice does not carry the pin.
    way4tech_income_line_id = fields.Many2one(
        "way4tech.manpower.contract.income.line",
        string="Source Income Line",
        index=True, copy=False, ondelete="set null",
    )

    @api.depends("move_id.way4tech_tag_ids")
    def _compute_way4tech_line_tags(self):
        for line in self:
            line.way4tech_tag_ids = line.move_id.way4tech_tag_ids

    def _inverse_way4tech_line_tags(self):
        """Push a line-level Contract Tags edit up to the journal entry so the
        whole entry (and its other lines) stays consistent."""
        for line in self:
            if line.move_id:
                line.move_id.way4tech_tag_ids = line.way4tech_tag_ids

    def unlink(self):
        """Alzain Fix 2 (2026-08): when a block-owned invoice line is deleted in
        Accounting while the invoice is still DRAFT, remove its Manpower Invoice
        Block wizard row too, so the wizard mirrors the deletion. Guarded so the
        block→invoice reconcile (which deletes owned lines itself) does not try
        to double-remove an already-gone row."""
        if not self.env.context.get("way4tech_block_syncing"):
            rows = self.env["way4tech.manpower.contract.income.line"].sudo().search(
                [("invoice_line_id", "in", self.ids)]
            )
            rows = rows.filtered(
                lambda r: r.invoice_block_id and r.invoice_id
                and r.invoice_id.state == "draft"
            )
            if rows:
                rows.with_context(
                    way4tech_block_syncing=True,
                    way4tech_skip_move_sync=True,
                ).unlink()
        return super().unlink()
