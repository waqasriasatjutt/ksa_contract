from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class Way4TechAssetRegister(models.Model):
    """
    Fixed Asset Register with automatic depreciation.
    Implements Straight Line and Declining Balance methods.
    Used because account.asset is an Enterprise-only module in Odoo 19.

    KSA accounting:
      Dr  Depreciation Expense (P&L)
      Cr  Accumulated Depreciation (Balance Sheet contra-asset)
    """
    _name = 'way4tech.asset.register'
    _description = 'Way4Tech Fixed Asset Register'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'name'

    # ── Identity ──────────────────────────────────────────────────────────────
    name = fields.Char(string='Asset Name', required=True, tracking=True)
    ref = fields.Char(string='Asset Code', readonly=True, copy=False,
                      help='Auto-generated unique reference for this asset.')
    category = fields.Selection([
        ('vehicle', 'Vehicle / Truck'),
        ('machinery', 'Machinery / Equipment'),
        ('tools', 'Tools & Instruments'),
        ('furniture', 'Furniture & Fixtures'),
        ('building', 'Building / Property'),
        ('it', 'IT Equipment'),
        ('other', 'Other'),
    ], string='Category', required=True, default='other', tracking=True)
    fleet_vehicle_id = fields.Many2one(
        'fleet.vehicle', string='Linked Vehicle',
        help='Link to a fleet vehicle if this asset is a truck or bus.',
    )

    # ── Valuation ─────────────────────────────────────────────────────────────
    purchase_date = fields.Date(string='Purchase / Acquisition Date', required=True, tracking=True)
    purchase_value = fields.Monetary(
        string='Original Cost (SAR)', required=True, tracking=True,
        help='Total cost of the asset at acquisition including import duties and installation.',
    )
    residual_value = fields.Monetary(
        string='Salvage / Residual Value', default=0.0,
        help='Estimated recoverable amount at end of useful life. Not depreciated.',
    )
    depreciable_amount = fields.Monetary(
        string='Depreciable Amount',
        compute='_compute_depreciable', store=True,
        help='Original Cost minus Salvage Value.',
    )

    # ── Method ────────────────────────────────────────────────────────────────
    depreciation_method = fields.Selection([
        ('straight_line', 'Straight Line'),
        ('declining', 'Declining Balance'),
    ], string='Depreciation Method', required=True, default='straight_line', tracking=True,
        help='Straight Line: equal monthly amount.\n'
             'Declining Balance: fixed % applied to remaining book value each period.')
    useful_life_months = fields.Integer(
        string='Useful Life (months)', required=True, default=60,
        help='Total depreciation period in months. E.g. 60 = 5 years.',
    )
    declining_rate = fields.Float(
        string='Annual Rate (%)', default=20.0, digits=(5, 2),
        help='Annual depreciation rate for Declining Balance method. E.g. 20 = 20% per year.',
    )

    # ── Accounts (KSA) ───────────────────────────────────────────────────────
    asset_account_id = fields.Many2one(
        'account.account', string='Asset Account', required=True,
        domain="[('account_type', '=', 'asset_fixed'), ('company_ids', 'in', [company_id])]",
        help='Balance sheet fixed asset account (e.g. 1500 – Property, Plant & Equipment).',
    )
    depreciation_account_id = fields.Many2one(
        'account.account', string='Accumulated Depreciation Account', required=True,
        domain="[('company_ids', 'in', [company_id])]",
        help='Contra-asset account for accumulated depreciation (e.g. 1590 – Acc. Depreciation).',
    )
    expense_account_id = fields.Many2one(
        'account.account', string='Depreciation Expense Account', required=True,
        domain="[('account_type', 'in', ['expense', 'expense_direct_cost']), ('company_ids', 'in', [company_id])]",
        help='P&L expense account (e.g. 6100 – Depreciation Expense).',
    )
    journal_id = fields.Many2one(
        'account.journal', string='Journal', required=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
    )
    analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id', store=True, readonly=True,
    )

    # ── Equipment Rentals (income from renting this asset out) ───────────────
    rental_ids = fields.One2many(
        'way4tech.equipment.rental', 'asset_register_id',
        string='Rental Agreements',
    )
    rental_count = fields.Integer(
        string='Rentals', compute='_compute_rental_stats',
    )
    rental_revenue_total = fields.Monetary(
        string='Total Rental Income',
        compute='_compute_rental_stats',
        help='Sum of revenue from all non-cancelled rental agreements on this asset.',
    )

    # ── Status & Summary ──────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('closed', 'Fully Depreciated'),
        ('disposed', 'Disposed'),
    ], string='Status', default='draft', tracking=True)
    depreciation_line_ids = fields.One2many(
        'way4tech.asset.depreciation.line', 'asset_id', string='Depreciation Schedule',
    )
    total_depreciated = fields.Monetary(
        string='Total Depreciated', compute='_compute_totals', store=True,
    )
    book_value = fields.Monetary(
        string='Net Book Value', compute='_compute_totals', store=True,
        help='Original Cost minus cumulative posted depreciation.',
    )
    line_count = fields.Integer(compute='_compute_totals', store=True)
    disposal_date = fields.Date(string='Disposal Date', tracking=True)
    notes = fields.Text()

    # ── Compute ───────────────────────────────────────────────────────────────

    def _compute_rental_stats(self):
        for rec in self:
            active_rentals = rec.rental_ids.filtered(
                lambda r: r.state != 'cancelled'
            )
            rec.rental_count = len(active_rentals)
            rec.rental_revenue_total = sum(active_rentals.mapped('revenue'))

    def action_view_rentals(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Rental Agreements — %s') % self.name,
            'res_model': 'way4tech.equipment.rental',
            'view_mode': 'list,form',
            'domain': [('asset_register_id', '=', self.id)],
            'context': {
                'default_asset_register_id': self.id,
                'default_equipment_name': self.name,
            },
        }

    @api.depends('purchase_value', 'residual_value')
    def _compute_depreciable(self):
        for rec in self:
            rec.depreciable_amount = max(0.0, rec.purchase_value - rec.residual_value)

    @api.depends('depreciation_line_ids.state', 'depreciation_line_ids.depreciation_amount',
                 'purchase_value')
    def _compute_totals(self):
        for rec in self:
            posted = rec.depreciation_line_ids.filtered(lambda l: l.state == 'posted')
            total_dep = sum(posted.mapped('depreciation_amount'))
            rec.total_depreciated = total_dep
            rec.book_value = rec.purchase_value - total_dep
            rec.line_count = len(rec.depreciation_line_ids)

    # ── Create ────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('ref'):
                vals['ref'] = self.env['ir.sequence'].next_by_code(
                    'way4tech.asset.register'
                ) or '/'
        return super().create(vals_list)

    # ── Business Logic ────────────────────────────────────────────────────────

    def action_start_depreciation(self):
        """Validate, generate full schedule and move to Running."""
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only Draft assets can be started.'))
            if rec.depreciation_line_ids:
                raise UserError(_(
                    'A depreciation schedule already exists.\n'
                    'Use "Reset to Draft" to clear it and regenerate.'
                ))
            if rec.useful_life_months <= 0:
                raise UserError(_('Useful Life must be greater than zero.'))
            rec._generate_depreciation_schedule()
            rec.state = 'running'
            rec.message_post(body=_('Depreciation started. %d lines generated.') % rec.line_count)

    def _generate_depreciation_schedule(self):
        """Compute and batch-create all depreciation lines."""
        from dateutil.relativedelta import relativedelta  # noqa
        lines = []
        start = self.purchase_date.replace(day=1)
        depreciable = self.depreciable_amount

        if self.depreciation_method == 'straight_line':
            if self.useful_life_months == 0:
                return
            base_amount = round(depreciable / self.useful_life_months, 2)
            cumulative = 0.0
            book = self.purchase_value
            amount_left = depreciable
            for i in range(1, self.useful_life_months + 1):
                dep_date = start + relativedelta(months=i)
                if i == self.useful_life_months:
                    dep_amount = round(amount_left, 2)
                else:
                    dep_amount = base_amount
                amount_left = round(amount_left - dep_amount, 2)
                cumulative = round(cumulative + dep_amount, 2)
                book = round(book - dep_amount, 2)
                lines.append({
                    'asset_id': self.id,
                    'sequence': i,
                    'date': dep_date,
                    'depreciation_amount': dep_amount,
                    'cumulative_depreciation': cumulative,
                    'book_value': max(book, self.residual_value),
                    'state': 'draft',
                })
        else:
            # Declining Balance
            annual_rate = self.declining_rate / 100.0
            monthly_rate = 1.0 - (1.0 - annual_rate) ** (1.0 / 12.0)
            book = self.purchase_value
            cumulative = 0.0
            for i in range(1, self.useful_life_months + 1):
                dep_date = start + relativedelta(months=i)
                depreciable_now = book - self.residual_value
                if depreciable_now <= 0.001:
                    break
                if i == self.useful_life_months:
                    dep_amount = round(depreciable_now, 2)
                else:
                    dep_amount = round(depreciable_now * monthly_rate, 2)
                book = round(book - dep_amount, 2)
                cumulative = round(cumulative + dep_amount, 2)
                lines.append({
                    'asset_id': self.id,
                    'sequence': i,
                    'date': dep_date,
                    'depreciation_amount': dep_amount,
                    'cumulative_depreciation': cumulative,
                    'book_value': max(book, self.residual_value),
                    'state': 'draft',
                })

        if lines:
            self.env['way4tech.asset.depreciation.line'].create(lines)

    def action_post_current_depreciation(self):
        """Post the next pending depreciation line due today or earlier."""
        self.ensure_one()
        if self.state != 'running':
            raise UserError(_('Asset must be in Running state to post depreciation.'))
        today = fields.Date.today()
        due_lines = self.depreciation_line_ids.filtered(
            lambda l: l.state == 'draft' and l.date <= today
        ).sorted('sequence')
        if not due_lines:
            raise UserError(_('No pending depreciation lines are due today or earlier.'))
        due_lines[0].action_post()
        if not self.depreciation_line_ids.filtered(lambda l: l.state == 'draft'):
            self.state = 'closed'
            self.message_post(body=_('Asset fully depreciated and closed.'))

    def action_post_all_due(self):
        """Post all pending depreciation lines up to and including today."""
        self.ensure_one()
        if self.state != 'running':
            raise UserError(_('Asset must be in Running state.'))
        today = fields.Date.today()
        due_lines = self.depreciation_line_ids.filtered(
            lambda l: l.state == 'draft' and l.date <= today
        )
        if not due_lines:
            raise UserError(_('No pending depreciation lines due today or earlier.'))
        due_lines.action_post()
        if not self.depreciation_line_ids.filtered(lambda l: l.state == 'draft'):
            self.state = 'closed'
            self.message_post(body=_('Asset fully depreciated and closed.'))

    def action_dispose(self):
        """Mark asset as disposed."""
        self.ensure_one()
        self.write({'state': 'disposed', 'disposal_date': fields.Date.today()})
        self.message_post(body=_('Asset disposed on %s.') % fields.Date.today())

    def action_reset_to_draft(self):
        """Delete schedule and reset to draft (only if no posted lines)."""
        self.ensure_one()
        posted = self.depreciation_line_ids.filtered(lambda l: l.state == 'posted')
        if posted:
            raise UserError(_(
                'Cannot reset: %d depreciation lines are already posted.\n'
                'Reverse them first.'
            ) % len(posted))
        self.depreciation_line_ids.unlink()
        self.state = 'draft'
        self.message_post(body=_('Asset reset to Draft. Schedule cleared.'))

    @api.model
    def _cron_post_monthly_depreciation(self):
        """Monthly cron: auto-post all due depreciation lines."""
        today = fields.Date.today()
        due_lines = self.env['way4tech.asset.depreciation.line'].search([
            ('state', '=', 'draft'),
            ('date', '<=', today),
            ('asset_id.state', '=', 'running'),
        ])
        posted_count = 0
        for line in due_lines:
            try:
                line.action_post()
                posted_count += 1
            except Exception:
                pass
        # Auto-close fully depreciated assets
        running_assets = self.search([('state', '=', 'running')])
        for asset in running_assets:
            if not asset.depreciation_line_ids.filtered(lambda l: l.state == 'draft'):
                asset.state = 'closed'


class Way4TechAssetDepreciationLine(models.Model):
    """Single depreciation period in the asset schedule."""
    _name = 'way4tech.asset.depreciation.line'
    _description = 'Asset Depreciation Schedule Line'
    _order = 'asset_id, sequence'

    asset_id = fields.Many2one(
        'way4tech.asset.register', required=True,
        ondelete='cascade', index=True,
    )
    sequence = fields.Integer(string='Period #')
    date = fields.Date(string='Depreciation Date', required=True)
    depreciation_amount = fields.Monetary(string='Depreciation Amount', required=True)
    cumulative_depreciation = fields.Monetary(string='Cumulative Depreciation')
    book_value = fields.Monetary(string='Net Book Value After')
    state = fields.Selection([
        ('draft', 'Scheduled'),
        ('posted', 'Posted'),
        ('reversed', 'Reversed'),
    ], string='Status', default='draft')
    move_id = fields.Many2one('account.move', string='Journal Entry', readonly=True)
    currency_id = fields.Many2one(
        'res.currency', related='asset_id.currency_id', store=True,
    )
    company_id = fields.Many2one(
        'res.company', related='asset_id.company_id', store=True,
    )

    def action_post(self):
        """
        Post depreciation journal entry:
          Dr  Depreciation Expense Account
          Cr  Accumulated Depreciation Account
        """
        for line in self.filtered(lambda l: l.state == 'draft'):
            asset = line.asset_id
            analytic_dist = (
                {str(asset.analytic_account_id.id): 100.0}
                if asset.analytic_account_id else False
            )
            debit_vals = {
                'name': f'Depreciation — {asset.name} (Period {line.sequence})',
                'account_id': asset.expense_account_id.id,
                'debit': line.depreciation_amount,
                'credit': 0.0,
            }
            credit_vals = {
                'name': f'Acc. Depreciation — {asset.name} (Period {line.sequence})',
                'account_id': asset.depreciation_account_id.id,
                'debit': 0.0,
                'credit': line.depreciation_amount,
            }
            if analytic_dist:
                debit_vals['analytic_distribution'] = analytic_dist

            move = self.env['account.move'].sudo().create({
                'move_type': 'entry',
                'date': line.date,
                'ref': f'Depreciation: {asset.name} | Period {line.sequence} | {line.date}',
                'journal_id': asset.journal_id.id,
                'company_id': asset.company_id.id,
                'line_ids': [(0, 0, debit_vals), (0, 0, credit_vals)],
            })
            move.action_post()
            line.write({'state': 'posted', 'move_id': move.id})

    def action_view_entry(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_('No journal entry linked to this line.'))
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.move_id.id,
        }
