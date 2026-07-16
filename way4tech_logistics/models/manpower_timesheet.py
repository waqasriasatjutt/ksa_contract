from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class Way4TechManpowerTimesheet(models.Model):
    _name = 'way4tech.manpower.timesheet'
    _description = 'Manpower Contract Timesheet'
    _order = 'contract_id, date, id'

    contract_id = fields.Many2one(
        comodel_name='way4tech.manpower.contract',
        string='Contract',
        required=True,
        ondelete='cascade',
        index=True,
    )
    date = fields.Date(string='Date', default=fields.Date.today)
    # P6: dual-entry mode. Way 1 uses (start_date, end_date, per_day_hours);
    # Way 2 uses (date, hours). Only one mode is active per line — the other
    # side is disabled via readonly attrs in the view.
    start_date = fields.Date(string='Start Date')
    end_date = fields.Date(string='End Date')
    per_day_hours = fields.Float(string='Per Day Allowed Hours', digits=(16, 2))
    employee_id = fields.Many2one(comodel_name='hr.employee', string='Employee')
    description = fields.Char(string='Description')
    hours = fields.Float(string='Hours', digits=(16, 2))
    rate = fields.Monetary(
        string='Rate',
        currency_field='currency_id',
        help='P6: per-line billing rate. Replaces the contract-header Hourly Rate.',
    )
    tag_ids = fields.Many2many(
        'way4tech.tag',
        'way4tech_timesheet_tag_rel',
        'line_id', 'tag_id',
        string='Contract Tags',
    )
    amount = fields.Monetary(
        string='Amount',
        compute='_compute_amount',
        currency_field='currency_id',
        help='Way 1 (range): calendar_days × per_day_hours × rate. '
             'Way 2 (single date): hours × rate.',
    )
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True, copy=False)
    state = fields.Selection(
        [('draft', 'Draft'), ('invoiced', 'Invoiced')],
        default='draft', readonly=True, copy=False,
    )

    # ── Employee salary cost side (mirrors the billing side) ──────────────────
    employee_hourly_rate = fields.Monetary(
        string="Employee Rate / Hour",
        currency_field='currency_id',
        help="Employee's hourly salary cost — kept separate from the client "
             "billing Rate above so cost tracking is unaffected by pricing.",
    )
    employee_cost = fields.Monetary(
        string='Employee Cost',
        compute='_compute_employee_cost',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='contract_id.company_id.currency_id',
        string='Currency',
        readonly=True,
    )

    @api.depends('hours', 'employee_hourly_rate')
    def _compute_employee_cost(self):
        for line in self:
            line.employee_cost = line.hours * line.employee_hourly_rate

    @api.depends('date', 'hours', 'rate', 'start_date', 'end_date', 'per_day_hours')
    def _compute_amount(self):
        """P6 dual-mode amount. Uses range mode if BOTH start_date + end_date
        are set; otherwise single-date mode. Calendar-day count is INCLUSIVE
        of both endpoints AND weekends (per spec)."""
        for line in self:
            rate = line.rate or 0.0
            if line.start_date and line.end_date and line.end_date >= line.start_date:
                days = (line.end_date - line.start_date).days + 1
                line.amount = days * (line.per_day_hours or 0.0) * rate
            else:
                line.amount = (line.hours or 0.0) * rate

    # NOTE (2026-07-17): removed the two @api.onchange handlers that
    # cross-cleared date/hours vs start_date/end_date/per_day_hours.
    # Their side-effect writes mutated OTHER cells in the same row on every
    # date pick → editable-list widget re-rendered the row → focus bounced
    # back into the date input → picker looped. Mode-exclusivity is still
    # enforced at save time by _check_one_mode below (@api.constrains), so
    # the UX contract is preserved without the row-refocus bug.

    @api.constrains('start_date', 'end_date')
    def _check_range_order(self):
        for line in self:
            if line.start_date and line.end_date and line.end_date < line.start_date:
                raise ValidationError(_('End Date must be on or after Start Date.'))

    @api.constrains('date', 'start_date', 'end_date')
    def _check_one_mode(self):
        for line in self:
            has_range = bool(line.start_date and line.end_date)
            has_single = bool(line.date)
            if not has_range and not has_single:
                raise ValidationError(_(
                    'Fill either a single Date (with Hours) OR a Start/End Date '
                    'range (with Per Day Allowed Hours) — one mode is required.'
                ))

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        """Auto-fill employee hourly rate from hr.contract if available."""
        if self.employee_id and not self.employee_hourly_rate:
            if 'hr.contract' not in self.env:
                return
            contract = self.env['hr.contract'].search([
                ('employee_id', '=', self.employee_id.id),
                ('state', '=', 'open'),
            ], limit=1)
            if contract and contract.wage:
                # Convert monthly wage to hourly rate (KSA: 30 days × 8 hours)
                self.employee_hourly_rate = contract.wage / (30.0 * 8.0)

    def action_create_invoice(self):
        """P6: per-line Create Invoice. Reuses the contract's income
        propagation (analytic + project + category + tags + PRO ref)."""
        for line in self:
            if line.invoice_id:
                raise UserError(_('This timesheet line has already been invoiced.'))
            contract = line.contract_id
            settings = self.env['way4tech.payroll.settings'].get_for_company(contract.company_id.id)
            distribution = contract._resolve_analytic_distribution(settings)
            sale_account = settings.manpower_income_account_id
            if not sale_account:
                raise UserError(_(
                    "No Manpower Income Account configured in Payroll & Accounting Setup."
                ))
            vat_tax = self.env['account.tax'].search([
                ('type_tax_use', '=', 'sale'),
                ('amount_type', '=', 'percent'),
                ('amount', '=', 15.0),
                ('company_id', '=', contract.company_id.id),
            ], limit=1)
            if not vat_tax:
                raise UserError(_('No 15% sales tax configured for this company.'))
            desc = line.description or _('Timesheet %s') % (line.date or line.start_date or '')
            line_vals = {
                'name': desc,
                'quantity': 1.0,
                'price_unit': line.amount or 0.0,
                'account_id': sale_account.id,
                'tax_ids': [(6, 0, [vat_tax.id])],
            }
            if distribution:
                line_vals['analytic_distribution'] = distribution
            move_vals = {
                'move_type': 'out_invoice',
                'partner_id': contract.client_id.id,
                'company_id': contract.company_id.id,
                'invoice_date': line.date or line.end_date or fields.Date.today(),
                'invoice_line_ids': [(0, 0, line_vals)],
            }
            if settings.manpower_journal_id:
                move_vals['journal_id'] = settings.manpower_journal_id.id
            if contract.way4tech_project_id:
                move_vals['way4tech_project_id'] = contract.way4tech_project_id.id
            if contract.way4tech_category_id:
                move_vals['way4tech_category_id'] = contract.way4tech_category_id.id
            all_tags = (contract.tag_ids | line.tag_ids)
            if all_tags:
                move_vals['way4tech_tag_ids'] = [(6, 0, all_tags.ids)]
            invoice = self.env['account.move'].create(move_vals)
            invoice.ref = contract._compose_reference_string(invoice=invoice)
            contract._apply_ksa_account_overrides(invoice)
            line.write({'invoice_id': invoice.id, 'state': 'invoiced'})
            contract.invoice_ids = [(4, invoice.id)]
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoice'),
            'res_model': 'account.move',
            'res_id': self[:1].invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
