from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class ManpowerProjectExpense(models.Model):
    """
    Project-level expense for a Manpower Contract (project type).

    Accounting flow (proper double-entry):
      Dr  Expense Account (wages / accommodation / utilities / furniture / other)
      Cr  Accounts Payable (vendor)

    The vendor bill is posted to accounts payable so it appears in AP aging,
    can be reconciled when paid, and is properly tracked in the GL.

    All bill lines carry the contract's analytic account so the full
    project P&L (revenue from invoice - costs from bills) is visible in
    Accounting → Reporting → Analytic Report.
    """
    _name = 'way4tech.manpower.project.expense'
    _description = 'Manpower Project Expense'
    _inherit = ['mail.thread', 'mail.activity.mixin',
                'way4tech.manpower.approval.mixin',
                'way4tech.manpower.docline.mixin']
    # See income-line comment: sorting by an editable date field causes a
    # row-position resort on every date pick in editable inline lists,
    # which re-renders + re-focuses → picker reopen loop. id desc only.
    _order = 'id desc'
    _rec_name = 'description'
    # CR5 item 2a: the line's "Files" dialog (docline mixin opener).
    _way4tech_attach_view_xmlid = 'way4tech_logistics.view_project_expense_attach_form'

    contract_id = fields.Many2one(
        comodel_name='way4tech.manpower.contract',
        string='Contract',
        required=True,
        ondelete='cascade',
        tracking=True,
    )
    # CR5 item 4: the contract's client, stored so the standalone Project
    # Expenses view can group by and column on Client. Related + store=True is
    # additive — Odoo maintains it from contract_id.client_id automatically;
    # no creation logic is touched.
    client_id = fields.Many2one(
        comodel_name='res.partner',
        related='contract_id.client_id',
        string='Client',
        store=True,
        readonly=True,
    )
    # P5 (2026-07-15): rename semantics — "date" kept as accounting_date-alias
    # for BC; new bill_date (invoice_date on the bill) exposed separately.
    # NOTE (2026-07-17): tracking=True dropped from both date fields.
    # mail.thread's tracking hook fires on every write, which combined with
    # `_order = 'date desc, id desc'` was re-ordering + re-rendering the row
    # on every date pick → editable-list focus bounced into the picker → loop.
    # Auditability on dates is low-value (the created vendor bill retains its
    # own posted-date audit trail); prioritising UX correctness here.
    date = fields.Date(
        string='Accounting Date',
        required=True,
        # CR4 item 3: default from the contract's Start Date month, not today.
        default=lambda self: self._way4tech_default_period_date(),
        help='Posting date on the generated vendor bill (accounting_date).',
    )
    bill_date = fields.Date(
        string='Bill Date',
        default=fields.Date.today,
        help='Vendor invoice date shown on the bill (bill_date). Defaults to '
             'today; DD/MM/YYYY display.',
    )
    # CR2 G2: category_id is required so every line is bucketed into
    # Direct Cost or Operating Exp via category.expense_type. Default is
    # taken from the tab's context (category_bucket_default), letting each
    # notebook page pre-select the "Miscellaneous" seed of that bucket.
    # CR4 item 5: module-local product, shown on the Direct Cost tab only (the
    # view hides it on Operating Exp). No onchange -> never affects account/VAT.
    product_id = fields.Many2one(
        'way4tech.manpower.product', string='Product',
        help="Optional product from the module's own list. Does not affect "
             "the GL account or VAT.",
    )
    category_id = fields.Many2one(
        'way4tech.expense.category',
        string='Category',
        required=True,
        default=lambda self: self._default_category_id(),
        help='KSA expense category. Selecting it auto-fills the Expense '
             'Account from Payroll Settings → Expense Category → GL Account '
             'map, and decides whether this line lives in Direct Cost or '
             'Operating Exp tab via the category bucket.',
    )

    @api.model
    def _default_category_id(self):
        """Pick a sensible default per tab context so keyboard-first entry
        doesn't hit the required-field error on every new line."""
        bucket = self.env.context.get('category_bucket_default')
        if not bucket:
            return False
        Cat = self.env['way4tech.expense.category']
        # Prefer 'Miscellaneous' if it's in this bucket, else first by sequence
        return (
            Cat.search([('expense_type', '=', bucket), ('code', '=', 'miscellaneous')], limit=1)
            or Cat.search([('expense_type', '=', bucket)], order='sequence, name', limit=1)
        )
    tag_ids = fields.Many2many(
        'way4tech.tag',
        'way4tech_project_expense_tag_rel',
        'expense_id', 'tag_id',
        string='Contract Tags',
    )
    expense_type = fields.Selection(
        selection=[
            ('worker_wages', 'Worker Wages'),
            ('accommodation', 'Accommodation'),
            ('utilities', 'Utilities'),
            ('furniture', 'Furniture & Equipment'),
            ('transport', 'Transport'),
            ('other', 'Other'),
        ],
        string='Expense Type',
        required=True,
        default='worker_wages',
        tracking=True,
        help='Type determines the default GL expense account from Payroll & Accounting Setup. '
             'You can override the account on this line.',
    )
    description = fields.Char(
        string='Description',
        required=True,
        tracking=True,
        help='Brief description of the expense, e.g. "Wages for 12 workers — March 2026" '
             'or "Accommodation rent — Al Jubail site — March 2026".',
    )
    vendor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Vendor',
        required=True,
        domain=[('supplier_rank', '>', 0)],
        tracking=True,
        help='The supplier or payee for this expense. Required to create the vendor bill.\n'
             'For worker wages, this could be a representative worker, a payroll agent, '
             'or a generic "Project Workers" vendor you create in Contacts.',
    )
    account_id = fields.Many2one(
        comodel_name='account.account',
        string='Expense Account',
        check_company=True,
        tracking=True,
        help='GL account to debit on the vendor bill line. '
             'Auto-filled from Payroll & Accounting Setup based on expense type. '
             'Override here if needed for this specific expense.',
    )
    # ── CR3 P9 (v13.0): Quantity + Price columns on expense tabs ────────────
    # Mirrors the Project Income line pattern (qty × price = amount). Kept
    # writable (readonly=False) so legacy rows that only had `amount` can
    # still be edited freely; also so the back-sync from `bill_line_id`
    # (_sync_amount_from_move below) can write `amount` directly without
    # tripping a computed-field guard. Default qty = 1.0 matches
    # bill_line quantity default at action_create_bill.
    quantity = fields.Float(
        string='Quantity',
        default=1.0,
        # CR3-FINAL round 4, item 8: 'Product Unit of Measure' is not a real
        # precision name in Odoo 19 (the record is "Product Unit"), so this
        # resolved to the default. Pin 2 decimals explicitly.
        digits=(16, 2),
        help='Quantity for the vendor bill line. Amount auto-computes as '
             'Quantity × Price. Defaults to 1.',
    )
    # CR6 item 2: Float at "Product Price" precision (6 dp) instead of Monetary
    # (which rounds to the 2-dp currency), so a precise unit price reaches the
    # bill line exactly. The Amount column stays Monetary (currency-rounded).
    price = fields.Float(
        string='Price',
        digits='Product Price',
        help='Unit price for the vendor bill line (6-dp). Amount auto-computes '
             'as Quantity x Price; typing the exact Amount back-solves Price '
             '(three-way).',
    )
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        required=True,
        tracking=True,
        compute='_compute_amount_from_qty_price',
        store=True,
        readonly=False,
        help='Auto-computed as Quantity × Price (P9). Editable — a manual '
             'value stays until Quantity or Price is next edited, at which '
             'point the compute recalculates. Post-billing back-sync from '
             'the vendor bill line still overrides via context flag.',
    )

    # CR3 P9: recompute amount = qty × price only when qty or price is set;
    # skip when both are default (qty=1, price=0) OR when the back-sync
    # from bill_line_id is running (context flag). Guarantees legacy
    # amount-only rows (price=0, qty=1) aren't zeroed on -u.
    @api.depends('quantity', 'price')
    def _compute_amount_from_qty_price(self):
        for rec in self:
            if rec.env.context.get('way4tech_skip_move_sync'):
                continue
            # Data-safety guard: if price is 0 (legacy row / user hasn't
            # touched the new columns yet), don't zero the existing amount.
            if not rec.price:
                # Keep whatever amount already had (either legacy user-input
                # or zero for genuinely new empty rows).
                if not rec.amount:
                    rec.amount = 0.0
                continue
            rec.amount = (rec.quantity or 0.0) * (rec.price or 0.0)

    @api.onchange('amount')
    def _onchange_amount_threeway(self):
        """CR6 item 2: three-way back-solve Price from a typed Amount. Only
        this one direction is an onchange; the stored compute above re-derives
        amount = qty x price from the new price (6-dp), so there is no loop.
        Skipped when Quantity is 0."""
        if self.quantity:
            self.price = self.amount / self.quantity
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='contract_id.currency_id',
        string='Currency',
        readonly=True,
        store=True,
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        related='contract_id.analytic_account_id',
        string='Analytic Account',
        store=True,
        readonly=True,
        help='Inherited from the contract. Applied to the vendor bill line so all '
             'project costs appear in the Analytic Report alongside the contract revenue.',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='contract_id.company_id',
        string='Company',
        store=True,
        readonly=True,
    )
    bill_id = fields.Many2one(
        comodel_name='account.move',
        string='Vendor Bill',
        readonly=True,
        copy=False,
        help='Vendor bill created when you click "Create Vendor Bill". Read-only.',
    )
    # CR2 G4 amendment A: pin specific bill line for per-line sync-back.
    bill_line_id = fields.Many2one(
        'account.move.line',
        string='Bill Line',
        readonly=True, copy=False, ondelete='set null',
        help='CR2 G4: the account.move.line minted by Create Bill on this '
             'expense row. Sync back-reads price_subtotal from this line.',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('billed', 'Bill Created'),
        ],
        string='Status',
        default='draft',
        readonly=True,
        tracking=True,
    )

    # ── Auto-fill account from expense type ──────────────────────────────────

    @api.onchange('expense_type')
    def _onchange_expense_type(self):
        if not self.expense_type:
            return
        settings = self.env['way4tech.payroll.settings'].get_for_company(
            (self.company_id or self.env.company).id
        )
        account = self._get_expense_account(settings)
        if account:
            self.account_id = account

    @api.onchange('category_id')
    def _onchange_category_id(self):
        """CR3-FINAL round 3, item 10: fill the GL account from configuration
        the moment a category is picked.

        Uses the guarded resolver, so a category mapped to a non-cost account
        (the Building Maintenance → 120006 InterCompany Petty cash case) fills
        NOTHING rather than a wrong account. action_create_bill then refuses
        with a message naming the category.
        """
        if not self.category_id:
            self.account_id = False
            return
        company = self.company_id or self.env.company
        self.account_id = self.category_id.resolve_expense_account(company)
        # CR3-FINAL round 4, item 7: tell the user AT SELECTION TIME that the
        # category has no account, instead of leaving the field silently blank
        # for them to notice. The hard refusal at Create Bill stays as a
        # backstop.
        if not self.account_id:
            return {'warning': {
                'title': _('No expense account configured'),
                'message': _(
                    'Category "%s" has no expense account mapped. Set it in '
                    'Configuration → Payroll & Accounting Setup → Manpower '
                    'Contracts → Expense Category map, or pick an account on '
                    'this line. The bill cannot be created until it has one.'
                ) % self.category_id.display_name,
            }}

    def _get_expense_account(self, settings):
        """Return the configured GL account for this expense type."""
        mapping = {
            'worker_wages': settings.project_wages_account_id,
            'accommodation': settings.project_accommodation_account_id,
            'utilities': settings.project_utilities_account_id,
            'furniture': settings.project_furniture_account_id,
            'transport': settings.project_transport_account_id,
            'other': settings.project_other_expense_account_id,
        }
        return mapping.get(self.expense_type)

    # ── Create vendor bill ────────────────────────────────────────────────────

    def action_create_bill(self):
        self.ensure_one()
        if self.bill_id:
            raise UserError(_('A vendor bill already exists for this expense.'))
        # CR4 item 7: a zero-amount bill is unusual but allowed. Ask for
        # confirmation via a dialog (NOT a UserError, which would just block
        # with no way to proceed). On confirm the wizard re-calls this action
        # with the skip flag set.
        if not (self.amount or 0.0) and not self.env.context.get(
                'way4tech_skip_zero_bill_check'):
            return {
                'type': 'ir.actions.act_window',
                'name': _('Zero-Amount Bill'),
                'res_model': 'way4tech.zero.bill.confirm.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {'default_expense_id': self.id},
            }
        if not self.vendor_id:
            raise UserError(_('Please set a vendor before creating the bill.'))
        # CR3-FINAL Part A: per-item approval, consumed on creation.
        self.contract_id._require_month_approval(record=self)
        if not self.account_id and self.category_id:
            # CR3-FINAL round 3, item 10: name the category and refuse, rather
            # than posting to whatever account happened to be lying around.
            self.account_id = self.category_id.resolve_expense_account(
                self.company_id or self.env.company, raise_if_missing=True,
            )
        if not self.account_id:
            raise UserError(_(
                'No expense account set. Please configure the account in '
                'Configuration → Payroll & Accounting Setup → Project Expenses, '
                'or set it directly on this expense line.'
            ))
        # CR2 G2: invoice-first rule now applies ONLY to Direct Cost bills.
        # Default-strict: if category_id is somehow missing (legacy row,
        # data corruption), TREAT AS DIRECT to preserve pre-G2 behavior.
        # Operating Exp bills post freely.
        _is_direct = (not self.category_id) or self.category_id.expense_type == 'direct'
        if _is_direct and not self.contract_id.invoice_ids:
            raise ValidationError(_(
                'Cannot create a vendor bill for this Direct Cost expense — '
                'the parent contract has no customer invoice yet. Create the '
                'customer invoice first (Project Income tab or the "Create '
                'Invoice" contract-header button); the Direct Cost bill will '
                'then inherit the invoice number as part of its Payment '
                'Reference. Operating Exp bills are not subject to this '
                'restriction.'
            ))

        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)

        # CR3 P9: if Quantity + Price were used (price > 0), carry them to
        # the bill line. Legacy rows with only amount populated fall back
        # to qty=1 × price_unit=amount (backwards compat, matches pre-P9
        # behaviour so existing flows are unbroken).
        if self.price:
            bl_quantity = self.quantity or 1.0
            bl_price = self.price
        else:
            bl_quantity = 1.0
            bl_price = self.amount
        # CR4 item 5c: product name above the description on the bill line.
        _pname = self.product_id.name or ''
        _pdesc = self.description or ''
        _bl_name = ('%s\n%s' % (_pname, _pdesc)) if (_pname and _pdesc) \
            else (_pname or _pdesc)
        bill_line_vals = {
            'name': _bl_name,
            'quantity': bl_quantity,
            'price_unit': bl_price,
            'account_id': self.account_id.id,
        }
        # CR2 G2: apply the category's Input VAT tax (if configured on the
        # settings map row) to the bill line so the purchase-side VAT posts.
        # Direct Cost REQUIRES an Input VAT tax to be configured — mirrors
        # the hard-fail pattern used for Output VAT on Project Income
        # invoices. Operating Exp missing tax silently skips (VAT-free).
        _map_row = settings.manpower_expense_category_account_ids.filtered(
            lambda m: m.category_id == self.category_id
        )[:1]
        if _map_row and _map_row.input_vat_tax_id:
            bill_line_vals['tax_ids'] = [(6, 0, [_map_row.input_vat_tax_id.id])]
        elif _is_direct:
            raise UserError(_(
                'No Input VAT tax configured for category "%s" (Direct Cost). '
                'Configure it in Configuration → Payroll & Accounting Setup → '
                'Manpower Contracts tab → Expense Category map, so the '
                'purchase-side VAT posts correctly on this Direct Cost bill.'
            ) % (self.category_id.name if self.category_id else '(none)'))
        # Reuse the contract's analytic distribution (multi-account) with
        # legacy single-analytic + company default as fallbacks. Same helper
        # used for customer-side invoices.
        distribution = self.contract_id._resolve_analytic_distribution(settings)
        if distribution:
            bill_line_vals['analytic_distribution'] = distribution

        journal = settings.project_expense_journal_id or self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.vendor_id.id,
            # bill_date -> account.move.invoice_date (vendor invoice date)
            # accounting date -> account.move.date
            'invoice_date': self.bill_date or self.date,
            'date': self.date,
            'company_id': self.company_id.id,
            'ref': '%s / %s' % (self.contract_id.name, self.description),
            'invoice_line_ids': [(0, 0, bill_line_vals)],
        }
        # P3: mirror contract-composite reference onto the bill's payment_reference.
        bill_vals['payment_reference'] = self.contract_id._compose_reference_string(
            invoice=self.contract_id.invoice_ids[:1]
        )
        if journal:
            bill_vals['journal_id'] = journal.id

        # Project + Entry Category from the contract propagate onto the
        # vendor-bill header. Contract's explicit choice wins; fall back to
        # the generic "Others" category if the contract has none.
        if self.contract_id.way4tech_project_id:
            bill_vals['way4tech_project_id'] = self.contract_id.way4tech_project_id.id
        if self.contract_id.way4tech_category_id:
            bill_vals['way4tech_category_id'] = self.contract_id.way4tech_category_id.id
        else:
            _category = self.env.ref('way4tech_logistics.category_others', raise_if_not_found=False)
            if _category:
                bill_vals['way4tech_category_id'] = _category.id
        all_tags = (self.contract_id.tag_ids | self.tag_ids)
        if all_tags:
            bill_vals['way4tech_tag_ids'] = [(6, 0, all_tags.ids)]
        bill = self.env['account.move'].create(bill_vals)
        self.contract_id._apply_ksa_account_overrides(bill)
        # CR2 G4: pin the specific bill line for per-line sync-back.
        self.write({
            'bill_id': bill.id,
            'bill_line_id': bill.invoice_line_ids[:1].id or False,
            'state': 'billed',
        })
        # CR3-FINAL Part A: burn the approval; it unlocks nothing further.
        self.contract_id._consume_approval(self)

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
            raise UserError(_('No vendor bill linked to this expense.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'res_id': self.bill_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _sync_amount_from_move(self, move):
        """CR2 G4 amendment A: pull price_subtotal from the pinned bill
        line back into this expense row. amount is a plain Monetary
        user-input field so direct write is safe. Skip legacy pre-G4
        rows without the pinned FK — never guess from amount_untaxed."""
        self.ensure_one()
        if move.move_type not in ('in_invoice', 'in_refund'):
            return
        if not self.bill_line_id:
            return
        new_amount = self.bill_line_id.price_subtotal or 0.0
        if new_amount != self.amount:
            self.with_context(way4tech_skip_move_sync=True).write({'amount': new_amount})

    def unlink(self):
        """CR2 G4 item 4/5: block deletion only when linked vendor bill is
        POSTED (skeptic amendment E — allow delete for draft/cancelled)."""
        for line in self:
            move = line.bill_id
            if move and move.state == 'posted':
                raise UserError(_(
                    'Cannot delete this Project Expense line — the linked '
                    'vendor bill "%s" is POSTED. Reset the bill to draft or '
                    'cancel it from the Accounting menu first, then retry.'
                ) % move.display_name)
        return super().unlink()
