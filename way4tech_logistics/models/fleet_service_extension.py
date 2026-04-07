from odoo import api, fields, models, _
from odoo.exceptions import UserError


class FleetVehicleLogServices(models.Model):
    """
    Extend fleet.vehicle.log.services with:
      - Way4Tech reference number (sequence)
      - Maintenance type selection (more specific than fleet's service_type_id)
      - Vendor bill creation workflow (bill_id)
      - Operational state workflow (draft → confirmed → done)
      - Analytic account for cost-centre reporting
      - Automatic truck operational_state toggle on confirm/done

    Field mapping from old way4tech.truck.maintenance:
      name             → way4tech_ref        (new — fleet has no sequence ref)
      truck_id         → vehicle_id          (standard fleet field)
      maintenance_date → date                (standard fleet field)
      description      → notes               (standard fleet field)
      vendor_id        → vendor_id           (standard fleet field)
      cost             → amount              (standard fleet field)
      maintenance_type → way4tech_maint_type (new — more specific than service_type_id)
      bill_id          → way4tech_bill_id    (new)
      analytic_account_id → way4tech_analytic_account_id (new)
      state            → way4tech_state      (new — fleet has no draft/done workflow)
    """
    _inherit = 'fleet.vehicle.log.services'

    way4tech_ref = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default=lambda self: _('New'),
        help='Auto-generated maintenance reference number.',
    )
    way4tech_maint_type = fields.Selection(
        selection=[
            ('preventive', 'Preventive'),
            ('corrective', 'Corrective'),
            ('accident', 'Accident Repair'),
            ('tyres', 'Tyres'),
            ('other', 'Other'),
        ],
        string='Maintenance Category',
        default='preventive',
        tracking=True,
        help='Category of maintenance work:\n'
             '• Preventive — scheduled servicing (oil change, filter, etc.)\n'
             '• Corrective — breakdown or unplanned repair\n'
             '• Accident Repair — damage from accident\n'
             '• Tyres — tyre replacement or rotation\n'
             '• Other — any other maintenance type',
    )
    way4tech_bill_id = fields.Many2one(
        comodel_name='account.move',
        string='Vendor Bill',
        readonly=True,
        copy=False,
        help='Vendor bill (in_invoice) created when you click "Create Vendor Bill". '
             'Read-only — generated automatically.',
    )
    way4tech_analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        help='Analytic account for this maintenance cost.\n'
             'Priority: (1) this field → (2) vehicle\'s analytic account → '
             '(3) company default in Payroll & Accounting Setup.\n\n'
             'Applied to the vendor bill line so this cost appears in the vehicle\'s '
             'Analytic Report alongside trip revenue.',
    )
    way4tech_state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('done', 'Done'),
        ],
        string='Service State',
        default='draft',
        tracking=True,
        copy=False,
        help='Draft: maintenance planned but not yet started.\n'
             'Confirmed: maintenance in progress — truck operational status set to '
             '"Under Maintenance" automatically.\n'
             'Done: maintenance complete — truck operational status restored to "Active".',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
        store=True,
    )

    # ── Sequence on create ────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('way4tech_ref', _('New')) == _('New'):
                vals['way4tech_ref'] = self.env['ir.sequence'].next_by_code(
                    'way4tech.truck.maintenance'
                ) or _('New')
        return super().create(vals_list)

    # ── Workflow ──────────────────────────────────────────────────────────────

    def action_confirm(self):
        self.ensure_one()
        self.way4tech_state = 'confirmed'
        if self.vehicle_id and self.vehicle_id.operational_state == 'active':
            self.vehicle_id.operational_state = 'maintenance'

    def action_done(self):
        self.ensure_one()
        self.way4tech_state = 'done'
        if self.vehicle_id and self.vehicle_id.operational_state == 'maintenance':
            self.vehicle_id.operational_state = 'active'

    def action_reset_draft(self):
        self.ensure_one()
        self.way4tech_state = 'draft'

    # ── Vendor bill creation ──────────────────────────────────────────────────

    def action_create_bill(self):
        self.ensure_one()
        if self.way4tech_bill_id:
            raise UserError(_('A vendor bill already exists for this maintenance record.'))
        if not self.vendor_id:
            raise UserError(_('Please set a service vendor before creating a bill.'))
        if not self.amount:
            raise UserError(_('Maintenance cost is zero. Please enter the cost first.'))

        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)
        analytic = (
            self.way4tech_analytic_account_id
            or (self.vehicle_id and self.vehicle_id.analytic_account_id)
            or settings.default_analytic_account_id
        )

        description = '%s - %s' % (
            self.way4tech_ref,
            (self.notes or '')[:60] if self.notes else self.service_type_id.name or '',
        )
        bill_line_vals = {
            'name': description,
            'quantity': 1.0,
            'price_unit': self.amount,
        }
        if settings.truck_expense_account_id:
            bill_line_vals['account_id'] = settings.truck_expense_account_id.id
        if analytic:
            bill_line_vals['analytic_distribution'] = {str(analytic.id): 100}

        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.vendor_id.id,
            'invoice_date': self.date,
            'company_id': self.company_id.id,
            'invoice_line_ids': [(0, 0, bill_line_vals)],
        }
        _category = self.env.ref('way4tech_logistics.category_maintenance', raise_if_not_found=False)
        if _category:
            bill_vals['way4tech_category_id'] = _category.id
        bill = self.env['account.move'].create(bill_vals)
        self.way4tech_bill_id = bill.id

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
        if not self.way4tech_bill_id:
            raise UserError(_('No vendor bill linked to this record.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'res_id': self.way4tech_bill_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
