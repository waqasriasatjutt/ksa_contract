from odoo import api, fields, models, _
from odoo.exceptions import UserError


class Way4TechTruckMaintenance(models.Model):
    _name = 'way4tech.truck.maintenance'
    _description = 'Truck Maintenance Log'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'maintenance_date desc, name desc'

    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default=lambda self: _('New'),
    )
    truck_id = fields.Many2one(
        comodel_name='fleet.vehicle',
        string='Truck',
        required=True,
        tracking=True,
    )
    maintenance_date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    maintenance_type = fields.Selection(
        selection=[
            ('preventive', 'Preventive'),
            ('corrective', 'Corrective'),
            ('accident', 'Accident Repair'),
            ('other', 'Other'),
        ],
        string='Type',
        default='preventive',
        tracking=True,
    )
    description = fields.Text(string='Description', required=True)
    vendor_id = fields.Many2one(
        comodel_name='res.partner',
        string='Service Vendor',
        domain=[('supplier_rank', '>', 0)],
    )
    cost = fields.Monetary(
        string='Cost',
        currency_field='currency_id',
        tracking=True,
    )
    bill_id = fields.Many2one(
        comodel_name='account.move',
        string='Vendor Bill',
        readonly=True,
        copy=False,
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
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
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
            ('done', 'Done'),
        ],
        string='Status',
        default='draft',
        tracking=True,
        copy=False,
    )
    notes = fields.Text(string='Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'way4tech.truck.maintenance'
                ) or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        self.ensure_one()
        self.state = 'confirmed'
        # Automatically set truck to maintenance status
        if self.truck_id.operational_state == 'active':
            self.truck_id.operational_state = 'maintenance'

    def action_done(self):
        self.ensure_one()
        self.state = 'done'
        # Restore truck to active when maintenance is done
        if self.truck_id.operational_state == 'maintenance':
            self.truck_id.operational_state = 'active'

    def action_reset_draft(self):
        self.ensure_one()
        self.state = 'draft'

    def action_create_bill(self):
        self.ensure_one()
        if not self.vendor_id:
            raise UserError(_('Please set a service vendor before creating a bill.'))
        if not self.cost:
            raise UserError(_('Maintenance cost is zero. Please enter the cost first.'))

        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)
        analytic = self.analytic_account_id or self.truck_id.analytic_account_id or settings.default_analytic_account_id

        bill_line_vals = {
            'name': '%s - %s' % (self.name, self.description[:60] if self.description else ''),
            'quantity': 1.0,
            'price_unit': self.cost,
        }
        if settings.truck_expense_account_id:
            bill_line_vals['account_id'] = settings.truck_expense_account_id.id
        if analytic:
            bill_line_vals['analytic_distribution'] = {str(analytic.id): 100}

        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.vendor_id.id,
            'invoice_date': self.maintenance_date,
            'company_id': self.company_id.id,
            'invoice_line_ids': [(0, 0, bill_line_vals)],
        }
        bill = self.env['account.move'].create(bill_vals)
        self.write({'bill_id': bill.id})
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
            raise UserError(_('No vendor bill linked to this record.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'res_id': self.bill_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
