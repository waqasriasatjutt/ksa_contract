import logging
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Notify this many days before an expiry date
EXPIRY_WARNING_DAYS = 60


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

    # ── Vehicle Identification ────────────────────────────────────────────────
    way4tech_sequence = fields.Char(
        string='Fleet Sequence #',
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        help='Auto-generated fleet sequence number.',
    )
    chassis_number = fields.Char(
        string='Chassis #',
        tracking=True,
        help='VIN / chassis number (metal plate).',
    )
    plate_type = fields.Selection(
        selection=[
            ('private', 'Private'),
            ('public', 'Public'),
        ],
        string='Plate Type',
        default='private',
        tracking=True,
        help='Saudi plate classification. Public plates require an operation card.',
    )

    # ── Vehicle Classification ────────────────────────────────────────────────
    vehicle_category = fields.Selection(
        selection=[
            ('car', 'Car'),
            ('bike', 'Bike / Motorcycle'),
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
            ('sponsored', 'Sponsored'),
            ('sold', 'Sold'),
        ],
        string='Ownership Type',
        required=True,
        default='own',
        tracking=True,
        help='Company Owned: no investor profit share.\n'
             'Investor Owned: monthly profit share calculated and paid to investor.\n'
             'Sponsored: vehicle covered by a sponsor, no profit share.\n'
             'Sold: vehicle no longer in active fleet (kept for history).',
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

    # ── Expiry Dates (Saudi compliance) ──────────────────────────────────────
    registration_expiry_date = fields.Date(
        string='Registration Card Expiry',
        tracking=True,
        help='Istimara (vehicle registration card) expiry date.',
    )
    inspection_expiry_date = fields.Date(
        string='Periodic Inspection Expiry',
        tracking=True,
        help='Fahes / periodic technical inspection expiry date.',
    )
    insurance_expiry_date = fields.Date(
        string='Insurance Expiry',
        tracking=True,
        help='Motor insurance expiry date.',
    )
    operation_card_expiry_date = fields.Date(
        string='Operation Card Expiry',
        tracking=True,
        help='Bitaqat tashgheel (operation card) expiry — public plates only.',
    )
    expiry_warning = fields.Char(
        string='Expiry Warning',
        compute='_compute_expiry_warning',
        help='Summary of expiring documents within the next %s days.' % EXPIRY_WARNING_DAYS,
    )
    has_expiry_warning = fields.Boolean(
        compute='_compute_expiry_warning',
        store=True,
        index=True,
    )

    # ── Driver Assignment ─────────────────────────────────────────────────────
    driver_assignment_ids = fields.One2many(
        'way4tech.vehicle.driver.assignment', 'vehicle_id',
        string='Driver Assignments',
    )
    current_driver_assignment_id = fields.Many2one(
        'way4tech.vehicle.driver.assignment',
        string='Current Driver',
        compute='_compute_current_driver',
        store=True,
    )
    current_driver_name = fields.Char(
        string='Driver',
        compute='_compute_current_driver',
        store=True,
    )
    current_driver_iqama = fields.Char(
        string='Driver Iqama #',
        compute='_compute_current_driver',
        store=True,
    )
    current_driver_handover_date = fields.Date(
        string='Handover Date',
        compute='_compute_current_driver',
        store=True,
    )

    # ── Smart button counts ───────────────────────────────────────────────────
    trip_count = fields.Integer(string='Trips', compute='_compute_way4tech_counts')
    payout_count = fields.Integer(string='P&L Records', compute='_compute_way4tech_counts')
    driver_assignment_count = fields.Integer(
        string='Driver Assignments', compute='_compute_way4tech_counts',
    )

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
            rec.driver_assignment_count = self.env['way4tech.vehicle.driver.assignment'].search_count(
                [('vehicle_id', '=', rec.id)]
            )

    # ── Expiry warning ───────────────────────────────────────────────────────
    @api.depends('registration_expiry_date', 'inspection_expiry_date',
                 'insurance_expiry_date', 'operation_card_expiry_date', 'plate_type')
    def _compute_expiry_warning(self):
        today = fields.Date.context_today(self)
        threshold = today + relativedelta(days=EXPIRY_WARNING_DAYS)
        for rec in self:
            warnings = []
            checks = [
                ('Registration', rec.registration_expiry_date),
                ('Inspection', rec.inspection_expiry_date),
                ('Insurance', rec.insurance_expiry_date),
            ]
            if rec.plate_type == 'public':
                checks.append(('Operation Card', rec.operation_card_expiry_date))
            for label, date in checks:
                if not date:
                    continue
                if date < today:
                    warnings.append('%s EXPIRED (%s)' % (label, date))
                elif date <= threshold:
                    days = (date - today).days
                    warnings.append('%s in %d days' % (label, days))
            rec.expiry_warning = ' | '.join(warnings)
            rec.has_expiry_warning = bool(warnings)

    # ── Current driver ───────────────────────────────────────────────────────
    @api.depends('driver_assignment_ids', 'driver_assignment_ids.return_date',
                 'driver_assignment_ids.state')
    def _compute_current_driver(self):
        for rec in self:
            current = rec.driver_assignment_ids.filtered(lambda a: a.state == 'current')[:1]
            rec.current_driver_assignment_id = current.id if current else False
            if current:
                rec.current_driver_name = current.employee_id.name or current.driver_name or ''
                rec.current_driver_iqama = current.driver_iqama or ''
                rec.current_driver_handover_date = current.handover_date
            else:
                rec.current_driver_name = False
                rec.current_driver_iqama = False
                rec.current_driver_handover_date = False

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
        Create a vendor bill for the next installment payment.
        The user confirms the bill and uses Odoo's 'Register Payment'
        to record the bank/cash outflow with proper reconciliation.
        """
        self.ensure_one()
        if not self.is_installment:
            raise UserError(_('This vehicle is not on an installment plan.'))
        if self.installment_remaining_balance <= 0:
            raise UserError(_('All installments for this vehicle have been fully paid.'))
        if not self.installment_vendor_id:
            raise UserError(_(
                'No Financing Vendor set on this vehicle.\n'
                'Please set the Financing Vendor field on the vehicle form.'
            ))

        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)
        if not settings.installment_payable_account_id:
            raise UserError(_(
                'Set the Installment Payable Account in '
                'Configuration → Payroll & Accounting Setup → Fleet & Trucks tab.'
            ))

        amount = min(self.installment_monthly_amount, self.installment_remaining_balance)
        analytic = self.analytic_account_id or settings.default_analytic_account_id

        bill_line = {
            'name': 'Installment #%d — %s' % (self.installments_paid + 1, self.name),
            'quantity': 1.0,
            'price_unit': amount,
            'account_id': settings.installment_payable_account_id.id,
        }
        if analytic:
            bill_line['analytic_distribution'] = {str(analytic.id): 100}

        inst_category = self.env.ref('way4tech_logistics.category_installment', raise_if_not_found=False)
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.installment_vendor_id.id,
            'invoice_date': fields.Date.today(),
            'ref': 'Installment #%d — %s' % (self.installments_paid + 1, self.license_plate or self.name),
            'company_id': self.company_id.id,
            'invoice_line_ids': [(0, 0, bill_line)],
        }
        if inst_category:
            bill_vals['way4tech_category_id'] = inst_category.id

        bill = self.env['account.move'].create(bill_vals)
        self.installments_paid += 1
        return {
            'type': 'ir.actions.act_window',
            'name': _('Installment Bill'),
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_driver_assignments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Driver Assignments'),
            'res_model': 'way4tech.vehicle.driver.assignment',
            'view_mode': 'list,form',
            'domain': [('vehicle_id', '=', self.id)],
            'context': {'default_vehicle_id': self.id},
        }

    # ── Sequence generation ─────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('way4tech_sequence') or vals.get('way4tech_sequence') == _('New'):
                vals['way4tech_sequence'] = self.env['ir.sequence'].next_by_code(
                    'way4tech.fleet.vehicle') or _('New')
        return super().create(vals_list)

    # ── Expiry cron ─────────────────────────────────────────────────────────
    @api.model
    def _cron_fleet_expiry_notifications(self):
        """Daily: email logistics managers about vehicles with documents expiring
        within EXPIRY_WARNING_DAYS (default 60) or already expired."""
        today = fields.Date.context_today(self)
        threshold = today + relativedelta(days=EXPIRY_WARNING_DAYS)

        # Find vehicles with any expiry date inside the warning window
        domain_any = ['|', '|', '|',
                      '&', ('registration_expiry_date', '!=', False),
                            ('registration_expiry_date', '<=', threshold),
                      '&', ('inspection_expiry_date', '!=', False),
                            ('inspection_expiry_date', '<=', threshold),
                      '&', ('insurance_expiry_date', '!=', False),
                            ('insurance_expiry_date', '<=', threshold),
                      '&', ('operation_card_expiry_date', '!=', False),
                            ('operation_card_expiry_date', '<=', threshold)]
        vehicles = self.search(domain_any)
        if not vehicles:
            _logger.info('Fleet expiry cron: no vehicles with documents expiring within %d days', EXPIRY_WARNING_DAYS)
            return True

        # Build one HTML report with vehicles grouped by urgency
        lines_expired = []
        lines_warning = []
        for v in vehicles:
            checks = [
                ('Registration', v.registration_expiry_date),
                ('Inspection', v.inspection_expiry_date),
                ('Insurance', v.insurance_expiry_date),
            ]
            if v.plate_type == 'public':
                checks.append(('Operation Card', v.operation_card_expiry_date))
            for label, date in checks:
                if not date or date > threshold:
                    continue
                days = (date - today).days
                row = '<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>' % (
                    v.license_plate or v.name or '',
                    v.current_driver_name or '',
                    label,
                    date,
                    '%d days' % days if days >= 0 else 'EXPIRED %d days ago' % (-days),
                )
                if days < 0:
                    lines_expired.append(row)
                else:
                    lines_warning.append(row)

        if not lines_expired and not lines_warning:
            return True

        def _table(title, rows):
            if not rows:
                return ''
            return (
                '<h3>%s</h3>'
                '<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse">'
                '<tr style="background:#eee"><th>Plate</th><th>Driver</th><th>Document</th>'
                '<th>Expiry Date</th><th>Status</th></tr>'
                '%s</table>'
            ) % (title, ''.join(rows))

        body = (
            '<p>Daily fleet compliance report — documents expiring within %d days.</p>'
            '%s%s'
            '<p style="color:#888">Auto-generated by way4tech_logistics.</p>'
        ) % (EXPIRY_WARNING_DAYS,
             _table('EXPIRED — urgent', lines_expired),
             _table('Expiring Soon', lines_warning))

        # Post to the logistics_manager group channel if it exists, otherwise log
        group = self.env.ref('way4tech_logistics.group_logistics_manager', raise_if_not_found=False)
        try:
            if group:
                users = self.env['res.users'].search([('groups_id', 'in', group.id)])
                partner_ids = users.mapped('partner_id').ids
                if partner_ids:
                    self.env['mail.thread'].message_notify(
                        partner_ids=partner_ids,
                        subject=_('Fleet Compliance: %d document(s) expiring') % (
                            len(lines_expired) + len(lines_warning)),
                        body=body,
                    )
        except Exception as e:
            _logger.warning('Fleet expiry cron notify failed: %s', e)
        _logger.info('Fleet expiry cron: %d expired, %d warning rows',
                     len(lines_expired), len(lines_warning))
        return True
