from odoo import api, fields, models, _
from odoo.exceptions import UserError

# SAR threshold above which non-managers need approval before posting
APPROVAL_THRESHOLD_PARAM = 'way4tech.approval_threshold'
DEFAULT_THRESHOLD = 500.0


class AccountMoveWay4Tech(models.Model):
    """
    Extends account.move with three new capabilities:

    1. MANDATORY ENTRY CATEGORY
       Every entry must have a category before it can be posted.
       Categories are managed by Admin in Configuration → Entry Categories.

    2. APPROVAL WORKFLOW
       Entries created by non-managers with amount > threshold (default 500 SAR)
       are blocked from posting and sent to managers for approval.
       Managers can approve (which posts) or reject (which returns to draft with reason).

    3. PREVIOUS EXPENSE DISPLAY
       When entering a bill/expense, the system shows the last entry
       for the same vendor — helps users spot repeated or unusual costs.
    """
    _inherit = 'account.move'

    # ── Entry Category (mandatory) ────────────────────────────────────────────
    way4tech_category_id = fields.Many2one(
        'way4tech.entry.category',
        string='Entry Category',
        tracking=True,
        help='Required: select a category before posting.\n'
             'Managed by Admin in Configuration → Entry Categories.',
    )

    # ── Client PO Link ────────────────────────────────────────────────────────
    way4tech_po_id = fields.Many2one(
        'way4tech.client.po',
        string='Client PO',
        tracking=True,
        help='Link this invoice to a Client PO for balance tracking.',
    )

    # ── Project + Tags (custom reporting dimensions) ──────────────────────────
    way4tech_project_id = fields.Many2one(
        'way4tech.project',
        string='Project',
        tracking=True,
        index=True,
        help='Project this entry belongs to. Managed in Configuration → Projects.',
    )
    way4tech_tag_ids = fields.Many2many(
        'way4tech.tag',
        'way4tech_move_tag_rel', 'move_id', 'tag_id',
        string='Contract Tags',
        help='Free tags for filtering/reporting. Managed in Configuration → '
             'Contract Tags (users can also create tags on the fly here).',
    )

    # ── Invoice Month (auto from Accounting Date) ─────────────────────────────
    way4tech_inv_month = fields.Char(
        string='INV Month',
        compute='_compute_way4tech_inv_month',
        store=True,
        index=True,
        help='Accounting month (e.g. Jan-2026) derived from the Accounting Date — '
             'so revenue is grouped in the correct P&L period even when the '
             'invoice is issued in a later month.',
    )

    @api.depends('date')
    def _compute_way4tech_inv_month(self):
        for rec in self:
            # MM/YYYY — e.g. accounting date 2026-07-15 -> "07/2026" (T1 2026-07-15
            # requirement). Matches ksa_invoice_period so form + list stay in sync.
            rec.way4tech_inv_month = rec.date.strftime('%m/%Y') if rec.date else False

    def _compute_date(self):
        """Keep a manually-picked Accounting Date on DRAFT invoices instead of
        letting it snap back to the Invoice Date.

        Odoo core computes `date` from `invoice_date` (@api.depends), so
        changing the Invoice Date overwrote the accounting date the user set.
        The client needs the accounting period independent of the document
        date (timesheets arrive late -> invoice issued next month but revenue
        belongs to the prior month). Once a DRAFT invoice already has an
        accounting date, keep it; Odoo still seeds it on creation and still
        handles posted moves and journal entries normally.
        """
        keep = self.filtered(
            lambda m: m.state == 'draft' and m.date
            and m.is_invoice(include_receipts=True)
        )
        for move in keep:
            move.date = move.date  # re-assert (satisfies the compute engine)
        rest = self - keep
        if rest:
            super(AccountMoveWay4Tech, rest)._compute_date()

    # ── Approval Workflow ─────────────────────────────────────────────────────
    way4tech_approval_state = fields.Selection([
        ('na', 'N/A'),
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Approval Status', default='na', tracking=True, copy=False)

    way4tech_rejection_reason = fields.Text(
        string='Rejection Reason', copy=False, tracking=True,
    )

    # ── Previous Expense Display ──────────────────────────────────────────────
    way4tech_prev_expense = fields.Char(
        string='Previous Related Entry',
        compute='_compute_way4tech_prev_expense',
        store=False,
    )
    way4tech_prev_expense_id = fields.Many2one(
        'account.move',
        string='Last Entry (Same Vendor)',
        compute='_compute_way4tech_prev_expense',
        store=False,
    )

    @api.depends('partner_id', 'move_type')
    def _compute_way4tech_prev_expense(self):
        for rec in self:
            if rec.partner_id and rec.move_type in (
                'in_invoice', 'in_receipt', 'entry', 'in_refund'
            ):
                origin_id = rec._origin.id if rec._origin else 0
                prev = self.search([
                    ('partner_id', '=', rec.partner_id.id),
                    ('move_type', '=', rec.move_type),
                    ('state', '=', 'posted'),
                    ('id', '!=', origin_id),
                ], order='date desc, id desc', limit=1)
                if prev:
                    rec.way4tech_prev_expense_id = prev.id
                    sym = prev.currency_id.symbol or 'SAR'
                    rec.way4tech_prev_expense = (
                        f'Last: {prev.name}  |  Date: {prev.date}  |  '
                        f'Amount: {sym} {prev.amount_total:,.2f}'
                    )
                else:
                    rec.way4tech_prev_expense_id = False
                    rec.way4tech_prev_expense = False
            else:
                rec.way4tech_prev_expense_id = False
                rec.way4tech_prev_expense = False

    # ── Override action_post ──────────────────────────────────────────────────

    def action_post(self):
        """
        Intercept posting:
        1. Enforce mandatory category for all logistics users.
        2. Block non-managers from posting entries > threshold SAR.
        """
        is_logistics_user = self.env.user.has_group('way4tech_logistics.group_logistics_user')
        is_manager = self.env.user.has_group('way4tech_logistics.group_logistics_manager')

        threshold = float(
            self.env['ir.config_parameter'].sudo().get_param(
                APPROVAL_THRESHOLD_PARAM, str(DEFAULT_THRESHOLD)
            )
        )

        for move in self:
            # Entry Category is OPTIONAL (client decision) - it never
            # blocks posting; used only for classification / reporting.
            # This also stops it breaking moves posted by wizards,
            # payments, bank reconciliation and other modules.

            # Approval threshold (non-managers only, not already approved)
            if (is_logistics_user and not is_manager
                    and move.way4tech_approval_state not in ('approved',)
                    and move.amount_total > threshold):
                move.way4tech_approval_state = 'pending'
                move._way4tech_notify_managers(threshold)
                raise UserError(_(
                    'This entry (%(amount).2f %(currency)s) exceeds the auto-post limit '
                    '(%(threshold).2f SAR).\n\n'
                    'It has been submitted to your Manager for approval.\n'
                    'You will be notified once reviewed.'
                ) % {
                    'amount': move.amount_total,
                    'currency': move.currency_id.name or 'SAR',
                    'threshold': threshold,
                })

        return super().action_post()

    # ── Approval Actions ──────────────────────────────────────────────────────

    def action_way4tech_approve(self):
        """Manager: approve pending entries and post them."""
        if not self.env.user.has_group('way4tech_logistics.group_logistics_manager'):
            raise UserError(_('Only Logistics Managers can approve journal entries.'))

        pending = self.filtered(lambda m: m.way4tech_approval_state == 'pending')
        if not pending:
            raise UserError(_('No entries are pending approval.'))

        # Mark approved first (bypasses threshold check in action_post)
        pending.write({'way4tech_approval_state': 'approved'})
        for move in pending:
            move.message_post(
                body=_('Entry <strong>approved</strong> by %s.') % self.env.user.name
            )

        # Now post them — super() bypasses our threshold check because state = approved
        super(AccountMoveWay4Tech, pending).action_post()

    def action_way4tech_reject(self):
        """Manager: open rejection wizard to enter reason and return to draft."""
        if not self.env.user.has_group('way4tech_logistics.group_logistics_manager'):
            raise UserError(_('Only Logistics Managers can reject journal entries.'))
        if not self.filtered(lambda m: m.way4tech_approval_state == 'pending'):
            raise UserError(_('No entries are pending approval.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject Entry — Provide Reason'),
            'res_model': 'way4tech.rejection.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_move_ids': [(6, 0, self.ids)]},
        }

    # ── Email Notification ────────────────────────────────────────────────────

    def _way4tech_notify_managers(self, threshold):
        """Send email to all logistics managers about a pending-approval entry."""
        try:
            group = self.env.ref('way4tech_logistics.group_logistics_manager')
            managers = group.users.filtered(lambda u: u.email)
            if not managers:
                return
            partner_name = self.partner_id.name if self.partner_id else '—'
            body = (
                f'<div style="font-family:Arial,sans-serif;">'
                f'<h3 style="color:#e63757;">Journal Entry Pending Your Approval</h3>'
                f'<table style="border-collapse:collapse;">'
                f'<tr><td style="padding:4px 10px;"><strong>Reference:</strong></td>'
                f'<td style="padding:4px 10px;">{self.name or "Draft"}</td></tr>'
                f'<tr><td style="padding:4px 10px;"><strong>Date:</strong></td>'
                f'<td style="padding:4px 10px;">{self.date}</td></tr>'
                f'<tr><td style="padding:4px 10px;"><strong>Amount:</strong></td>'
                f'<td style="padding:4px 10px;">'
                f'{self.amount_total:,.2f} {self.currency_id.name or "SAR"}</td></tr>'
                f'<tr><td style="padding:4px 10px;"><strong>Threshold:</strong></td>'
                f'<td style="padding:4px 10px;">{threshold:,.2f} SAR</td></tr>'
                f'<tr><td style="padding:4px 10px;"><strong>Partner:</strong></td>'
                f'<td style="padding:4px 10px;">{partner_name}</td></tr>'
                f'<tr><td style="padding:4px 10px;"><strong>Submitted by:</strong></td>'
                f'<td style="padding:4px 10px;">{self.env.user.name}</td></tr>'
                f'</table>'
                f'<p>Please log in to <strong>Way4Tech Logistics</strong> and open this entry '
                f'to <strong style="color:green;">Approve</strong> or '
                f'<strong style="color:red;">Reject</strong>.</p>'
                f'</div>'
            )
            for mgr in managers:
                self.env['mail.mail'].sudo().create({
                    'subject': (
                        f'[Way4Tech] Approval Required: '
                        f'{self.name or "New Entry"} — '
                        f'{self.amount_total:,.2f} {self.currency_id.name or "SAR"}'
                    ),
                    'body_html': body,
                    'email_to': mgr.email,
                    'email_from': self.env.company.email or 'noreply@way4tech.com',
                }).send()
        except Exception:
            # Never interrupt the user flow for email failures
            pass
