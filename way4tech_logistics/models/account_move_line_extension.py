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
