from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FleetVehicle(models.Model):
    """
    Extend fleet.vehicle with KSA logistics-specific fields:
      - vehicle_category  (truck / bus / flatbed / other)
      - ownership_type    (company-owned vs investor-owned)
      - installment       (for buses purchased on financing plan)
      - PPE asset fields  (purchase_value, asset_account_id)
      - operational_state (active / maintenance / inactive)
    """
    _inherit = 'fleet.vehicle'

    # ── Vehicle Classification ────────────────────────────────────────────────
    vehicle_category = fields.Selection(
        selection=[
            ('truck', 'Truck'),
            ('bus', 'Bus / Minibus'),
            ('flatbed', 'Flatbed / Low-Loader'),
            ('other', 'Other'),
        ],
        string='Vehicle Category',
        required=True,
        default='truck',
        tracking=True,
    )

    # ── Ownership ────────────────────────────────────────────────────────────
    ownership_type = fields.Selection(
        selection=[
            ('own', 'Company Owned'),
            ('investor', 'Investor Owned'),
        ],
        string='Ownership Type',
        required=True,
        default='own',
        tracking=True,
        help='Company Owned: no investor profit share.\n'
             'Investor Owned: monthly profit share calculated and paid to investor.',
    )
    investor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Investor',
        tracking=True,
        help='The investor who owns this vehicle. Required for investor-owned vehicles.',
    )
    profit_share_rate = fields.Float(
        string='Investor Profit Share %',
        default=50.0,
        digits=(5, 2),
        help='Percentage of gross profit paid to the investor (BRD: 50/50 split).\n'
             'Company gets 100% for company-owned vehicles.',
    )

    # ── Fixed Asset Tracking (Saudi PPE) ─────────────────────────────────────
    purchase_value = fields.Monetary(
        string='Purchase Value',
        currency_field='currency_id',
        tracking=True,
        help='Original purchase price for the fixed asset register.\n'
             'In Saudi accounting, vehicles are PPE debited to a Fixed Asset account.',
    )
    asset_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Fixed Asset Account',
        domain="[('account_type', '=', 'asset_fixed'), ('company_ids', 'in', [company_id])]",
        help='Balance sheet PPE account for this vehicle (e.g. 150010 – Motor Vehicles).\n'
             'KSA account type: asset_fixed. For reference / reporting only.',
    )

    # ── Installment / Financing (for installment buses) ──────────────────────
    is_installment = fields.Boolean(
        string='Purchased on Installment',
        default=False,
        tracking=True,
        help='Tick for vehicles purchased via a bank or dealer financing plan.',
    )
    installment_vendor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Financing Vendor',
        domain=[('supplier_rank', '>', 0)],
        help='The bank or dealer providing the installment financing.',
    )
    installment_total_price = fields.Monetary(
        string='Total Financed Price',
        currency_field='currency_id',
        help='Total price including any financing charges.',
    )
    installment_down_payment = fields.Monetary(
        string='Down Payment Paid',
        currency_field='currency_id',
    )
    installment_monthly_amount = fields.Monetary(
        string='Monthly Installment',
        currency_field='currency_id',
    )
    installment_start_date = fields.Date(
        string='First Installment Date',
    )
    installments_paid = fields.Integer(
        string='Installments Paid',
        default=0,
    )
    installment_total_months = fields.Integer(
        string='Total Installments',
        compute='_compute_installment_info',
        store=True,
    )
    installment_remaining_balance = fields.Monetary(
        string='Outstanding Balance',
        currency_field='currency_id',
        compute='_compute_installment_info',
        store=True,
        help='Remaining principal to be paid.',
    )
    installment_end_date = fields.Date(
        string='Est. Payoff Date',
        compute='_compute_installment_info',
        store=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
        store=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    # ── Assignment & Analytics ────────────────────────────────────────────────
    current_client_id = fields.Many2one(
        comodel_name='res.partner',
        string='Current Client',
        tracking=True,
        help='Client this vehicle is currently assigned to. Informational only.',
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        help='Cost centre for per-vehicle P&L in Accounting → Analytic Report.',
    )
    po_limit = fields.Monetary(
        string='PO Limit per Trip',
        currency_field='currency_id',
        help='Maximum revenue per single trip. Set 0 for no limit.',
    )
    operational_state = fields.Selection(
        selection=[
            ('active', 'Active'),
            ('maintenance', 'Under Maintenance'),
            ('inactive', 'Inactive'),
        ],
        string='Operational Status',
        default='active',
        tracking=True,
    )

    # ── Override model_id to make it optional ────────────────────────────────
    model_id = fields.Many2one(
        'fleet.vehicle.model',
        'Model',
        tracking=True,
        required=False,
    )

    # ── Installment Schedule ──────────────────────────────────────────────────
    installment_schedule_ids = fields.One2many(
        'way4tech.installment.schedule', 'vehicle_id',
        string='Installment Schedule',
    )
    installment_schedule_count = fields.Integer(
        string='Schedule Lines', compute='_compute_way4tech_counts',
    )

    # ── Smart button counts ───────────────────────────────────────────────────
    trip_count = fields.Integer(string='Trips', compute='_compute_way4tech_counts')
    payout_count = fields.Integer(string='P&L Records', compute='_compute_way4tech_counts')

    # ── Computed: installment info ────────────────────────────────────────────
    @api.depends(
        'is_installment', 'installment_total_price', 'installment_down_payment',
        'installment_monthly_amount', 'installments_paid', 'installment_start_date',
    )
    def _compute_installment_info(self):
        import math
        from dateutil.relativedelta import relativedelta
        for rec in self:
            if not rec.is_installment or not rec.installment_monthly_amount:
                rec.installment_total_months = 0
                rec.installment_remaining_balance = 0.0
                rec.installment_end_date = False
                continue
            financed = rec.installment_total_price - rec.installment_down_payment
            monthly = rec.installment_monthly_amount
            total_months = math.ceil(financed / monthly) if monthly > 0 else 0
            paid_amount = rec.installments_paid * monthly
            remaining = max(0.0, financed - paid_amount)
            end_date = False
            if rec.installment_start_date and total_months:
                end_date = rec.installment_start_date + relativedelta(months=total_months - 1)
            rec.installment_total_months = total_months
            rec.installment_remaining_balance = remaining
            rec.installment_end_date = end_date

    @api.depends('license_plate')
    def _compute_way4tech_counts(self):
        for rec in self:
            rec.trip_count = self.env['way4tech.truck.trip'].search_count(
                [('truck_id', '=', rec.id)]
            )
            rec.payout_count = self.env['way4tech.investor.payable'].search_count(
                [('truck_id', '=', rec.id)]
            )
            rec.installment_schedule_count = self.env['way4tech.installment.schedule'].search_count(
                [('vehicle_id', '=', rec.id)]
            )

    # ── Actions ──────────────────────────────────────────────────────────────
    def action_set_active(self):
        self.ensure_one()
        self.operational_state = 'active'

    def action_set_maintenance(self):
        self.ensure_one()
        self.operational_state = 'maintenance'

    def action_set_inactive(self):
        self.ensure_one()
        self.operational_state = 'inactive'

    def action_view_trips(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Trips'),
            'res_model': 'way4tech.truck.trip',
            'view_mode': 'list,form',
            'domain': [('truck_id', '=', self.id)],
            'context': {'default_truck_id': self.id},
        }

    def action_view_payouts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Profitability Records'),
            'res_model': 'way4tech.investor.payable',
            'view_mode': 'list,form',
            'domain': [('truck_id', '=', self.id)],
            'context': {'default_truck_id': self.id},
        }

    def action_view_installment_schedule(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Installment Schedule'),
            'res_model': 'way4tech.installment.schedule',
            'view_mode': 'list,form',
            'domain': [('vehicle_id', '=', self.id)],
            'context': {
                'default_vehicle_id': self.id,
                'default_amount': self.installment_monthly_amount,
            },
        }

    def action_generate_installment_schedule(self):
        """Auto-generate full installment schedule from vehicle financing fields."""
        self.ensure_one()
        if not self.is_installment:
            raise UserError(_('This vehicle is not on an installment plan.'))
        if not self.installment_start_date or not self.installment_monthly_amount:
            raise UserError(_(
                'Please set First Installment Date and Monthly Installment Amount first.'
            ))
        # Delete existing schedule
        self.installment_schedule_ids.unlink()
        # Generate new schedule
        from dateutil.relativedelta import relativedelta
        total_months = self.installment_total_months
        lines = []
        for i in range(1, total_months + 1):
            due_date = self.installment_start_date + relativedelta(months=i - 1)
            lines.append({
                'vehicle_id': self.id,
                'installment_number': i,
                'due_date': due_date,
                'amount': self.installment_monthly_amount,
            })
        if lines:
            self.env['way4tech.installment.schedule'].create(lines)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Installment Schedule'),
            'res_model': 'way4tech.installment.schedule',
            'view_mode': 'list,form',
            'domain': [('vehicle_id', '=', self.id)],
        }

    def action_pay_installment(self):
        """
        Record one monthly installment payment.
        Creates a draft journal entry: Dr Installment Payable / Cr (user fills bank).
        Also increments installments_paid counter.

        Saudi accounting:
          Dr  Installment Payable (liability_non_current / liability_current)
          Cr  Bank / Cash
        """
        self.ensure_one()
        if not self.is_installment:
            raise UserError(_('This vehicle is not on an installment plan.'))
        if self.installment_remaining_balance <= 0:
            raise UserError(_('All installments for this vehicle have been fully paid.'))

        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)
        if not settings.installment_payable_account_id:
            raise UserError(_(
                'Set the Installment Payable Account in '
                'Configuration → Payroll & Accounting Setup → Fleet & Trucks tab.'
            ))

        amount = min(self.installment_monthly_amount, self.installment_remaining_balance)
        # Credit side: bank/cash journal default account
        journal = settings.truck_expense_journal_id or self.env['account.journal'].search(
            [('type', 'in', ['bank', 'cash']), ('company_id', '=', self.company_id.id)],
            limit=1,
        )
        credit_account = journal.default_account_id if journal else False
        if not credit_account:
            raise UserError(_(
                'No bank/cash account found for the credit side of the installment entry.\n'
                'Set a Truck Expense Journal in Configuration → Payroll & Accounting Setup → Fleet & Trucks.'
            ))
        inst_category = self.env.ref('way4tech_logistics.category_installment', raise_if_not_found=False)
        move_vals = {
            'move_type': 'entry',
            'ref': 'Installment — %s' % (self.license_plate or self.name),
            'narration': 'Monthly installment payment — %s  (Installment #%d)' % (
                self.name, self.installments_paid + 1
            ),
            'date': fields.Date.today(),
            'company_id': self.company_id.id,
            'line_ids': [
                (0, 0, {
                    'name': 'Installment Payable — %s' % self.name,
                    'account_id': settings.installment_payable_account_id.id,
                    'debit': amount,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'Installment Payment — %s' % self.name,
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': amount,
                }),
            ],
        }
        if inst_category:
            move_vals['way4tech_category_id'] = inst_category.id
        if journal:
            move_vals['journal_id'] = journal.id
        move = self.env['account.move'].create(move_vals)
        self.installments_paid += 1
        return {
            'type': 'ir.actions.act_window',
            'name': _('Installment Payment Entry'),
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }
