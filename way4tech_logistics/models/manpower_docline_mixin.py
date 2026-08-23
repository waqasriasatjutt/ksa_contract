# -*- coding: utf-8 -*-
"""CR5 item 2 — attachments + document download for lines that GENERATE a
customer invoice or a vendor bill.

Mixed into exactly those line models (Project Income line, Project Expense,
Timesheet, Sales Person Commission, and the Invoice Block). NOT Project Budget,
which creates no document.

Everything here is ADDITIVE and display-layer only:
  * 2a — a Many2many to ir.attachment for user files, with a count, using
    standard attachment storage. No parallel mechanism.
  * 2b — a download control that reads the ALREADY-LINKED move (invoice_id /
    bill_id, whichever the concrete model has) and renders the correct report
    for that ONE document. Creation code is never touched.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class Way4TechManpowerDocLineMixin(models.AbstractModel):
    _name = 'way4tech.manpower.docline.mixin'
    _description = 'Manpower line — attachments + document download'

    # Each concrete model points this at its own tiny "Line Files & Document"
    # dialog form (an xml id). The paperclip button below opens that dialog so
    # the many2many_binary uploader renders in a FORM context (it is a
    # form-only widget — it does not render as a list column). Left None on the
    # abstract model and on any concrete model that only wants the download
    # control, in which case the opener falls back to the default form view.
    _way4tech_attach_view_xmlid = None

    # ── 2a: user attachments (multiple per line, standard ir.attachment) ──
    attachment_ids = fields.Many2many(
        'ir.attachment', string='Attachments',
        help='Supporting files for this line (receipts, supplier invoices, '
             'approvals). Stored as standard Odoo attachments.',
    )
    attachment_count = fields.Integer(
        string='# Files', compute='_compute_attachment_count',
        help='Number of files attached to this line.',
    )

    @api.depends('attachment_ids')
    def _compute_attachment_count(self):
        for rec in self:
            rec.attachment_count = len(rec.attachment_ids)

    # ── 2b: the generated document, resolved from the existing link ───────
    has_document = fields.Boolean(
        string='Has Document', compute='_compute_has_document',
        help='True when a customer invoice or vendor bill has been created '
             'from this line — the download control appears then.',
    )

    def _way4tech_document(self):
        """The move linked to this line via the EXISTING field. Read-only —
        never writes or creates anything."""
        self.ensure_one()
        for fname in ('invoice_id', 'bill_id'):
            if fname in self._fields and self[fname]:
                return self[fname]
        return self.env['account.move']

    @api.depends(lambda self: [
        f for f in ('invoice_id', 'bill_id') if f in self._fields
    ])
    def _compute_has_document(self):
        for rec in self:
            rec.has_document = bool(rec._way4tech_document())

    # ── Item 4 (2026-08): live payment status of the generated document ───
    # Read straight from Accounting's account.move.payment_state on every read
    # (compute, NOT stored -> always current; @api.depends invalidates it the
    # moment a payment is registered / reversed). Collapsed to the three states
    # the contract tabs show. Read-only display — no payment logic here.
    way4tech_payment_status = fields.Selection(
        [('unpaid', 'Unpaid'),
         ('partial', 'Partially Paid'),
         ('paid', 'Fully Paid')],
        string='Payment', compute='_compute_way4tech_payment_status',
    )

    @api.depends(lambda self: [
        '%s.payment_state' % f for f in ('invoice_id', 'bill_id')
        if f in self._fields
    ])
    def _compute_way4tech_payment_status(self):
        for rec in self:
            move = rec._way4tech_document()
            ps = move.payment_state if move else False
            if ps in ('paid', 'in_payment'):
                rec.way4tech_payment_status = 'paid'
            elif ps == 'partial':
                rec.way4tech_payment_status = 'partial'
            elif ps:
                rec.way4tech_payment_status = 'unpaid'
            else:
                rec.way4tech_payment_status = False

    # ── ITEM 1 (2026-08): the document's LIVE Accounting status ───────────
    # A single, purely-informational status the contract tabs show in place of
    # the raw internal state, so the label always matches what Accounting is
    # actually showing for the generated document:
    #   Draft          — no invoice/bill/entry created yet
    #   Created Draft  — the document was created but is still DRAFT in
    #                    Accounting (nothing confirmed/posted). This is the fix
    #                    for "shows Bill Created while the bill is still draft".
    #   Posted         — the document is posted/confirmed in Accounting (the
    #                    exact word core Accounting uses for account.move).
    # It is COMPUTED, NOT stored, and reads the move's live state on every read,
    # so a reset-to-draft in Accounting reverts it to Created Draft for EVERY
    # document type automatically (this is the ITEM 2 fix for Other Payable).
    # Because it is a read-only computed display field, it can NEVER block a
    # delete, edit or any other action — it is informational only.
    way4tech_doc_status = fields.Selection(
        [('draft', 'Draft'),
         ('created_draft', 'Created Draft'),
         ('posted', 'Posted')],
        string='Status', compute='_compute_way4tech_doc_status',
        help='Live Accounting status of the document created from this line — '
             'Draft (none yet), Created Draft (created but still draft in '
             'Accounting), or Posted (confirmed/posted). Informational only; '
             'it never affects delete or any other action.',
    )

    @api.depends(lambda self: [
        '%s.state' % f for f in ('invoice_id', 'bill_id', 'move_id')
        if f in self._fields
    ])
    def _compute_way4tech_doc_status(self):
        for rec in self:
            move = rec._way4tech_document()
            if not move or move.state == 'cancel':
                # No document, or it was cancelled (link is released) — back to
                # the pre-creation state.
                rec.way4tech_doc_status = 'draft'
            elif move.state == 'posted':
                rec.way4tech_doc_status = 'posted'
            else:  # account.move draft
                rec.way4tech_doc_status = 'created_draft'

    def action_download_document(self):
        """CR5 item 2b — download THIS line's document as a correct, complete
        PDF. Returns the proper report for that document type, for that single
        move only (ZATCA: never merged, never combined)."""
        self.ensure_one()
        move = self._way4tech_document()
        if not move:
            raise UserError(_('No invoice or bill has been created from this '
                              'line yet.'))
        if move.move_type in ('out_invoice', 'out_refund'):
            # Customer invoice → the KSA ZATCA tax invoice (QR, VAT), with the
            # standard invoice report as a fallback if the KSA module is absent.
            report = self.env.ref(
                'way4tech_ksa_tax_invoice.action_report_ksa_tax_invoice',
                raise_if_not_found=False,
            ) or self.env.ref('account.account_invoices')
        else:
            # Vendor bill → the standard account move document report.
            report = self.env.ref('account.account_invoices')
        return report.report_action(move)

    def action_open_attachments(self):
        """CR5 item 2a — open THIS line in a small dialog carrying the
        many2many_binary uploader (add / open supporting files) plus the
        document-download control. The paperclip button on the line calls
        this. Purely a UI opener — reads/writes nothing itself."""
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Line Files & Document'),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
        xmlid = self._way4tech_attach_view_xmlid
        if xmlid:
            view = self.env.ref(xmlid, raise_if_not_found=False)
            if view:
                action['views'] = [(view.id, 'form')]
        return action
