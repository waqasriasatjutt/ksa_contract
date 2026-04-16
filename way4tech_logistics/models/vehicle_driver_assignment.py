from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class VehicleDriverAssignment(models.Model):
    """Driver ↔ Vehicle assignment history (handover → return).

    A vehicle can have many past assignments but only ONE active at a time.
    The current active assignment drives the fleet.vehicle.current_driver_* fields.
    """
    _name = 'way4tech.vehicle.driver.assignment'
    _inherit = ['mail.thread']
    _description = 'Vehicle Driver Assignment'
    _order = 'handover_date desc, id desc'
    _rec_name = 'display_name'

    vehicle_id = fields.Many2one(
        'fleet.vehicle',
        string='Vehicle',
        required=True,
        ondelete='cascade',
        index=True,
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Driver (Employee)',
        help='Pick an existing employee, or leave blank and type a free-text driver name.',
    )
    driver_name = fields.Char(
        string='Driver Name',
        help='Free-text driver name if not an HR employee.',
    )
    driver_iqama = fields.Char(
        string='Driver Iqama #',
        tracking=True,
    )
    handover_date = fields.Date(
        string='Handover Date',
        required=True,
        default=fields.Date.context_today,
    )
    return_date = fields.Date(
        string='Return Date',
        help='When the driver returned the vehicle. Leave blank for the currently assigned driver.',
    )
    state = fields.Selection(
        selection=[
            ('current', 'Current'),
            ('returned', 'Returned'),
        ],
        string='Status',
        compute='_compute_state',
        store=True,
        index=True,
    )
    notes = fields.Text(string='Notes')
    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('return_date')
    def _compute_state(self):
        for rec in self:
            rec.state = 'returned' if rec.return_date else 'current'

    @api.depends('employee_id', 'driver_name', 'vehicle_id', 'handover_date')
    def _compute_display_name(self):
        for rec in self:
            who = rec.employee_id.name or rec.driver_name or _('(unnamed)')
            plate = rec.vehicle_id.license_plate or rec.vehicle_id.name or ''
            rec.display_name = '%s ← %s' % (plate, who) if plate else who

    @api.constrains('vehicle_id', 'return_date')
    def _check_single_current(self):
        for rec in self:
            if rec.return_date:
                continue
            dupes = self.search([
                ('vehicle_id', '=', rec.vehicle_id.id),
                ('return_date', '=', False),
                ('id', '!=', rec.id),
            ])
            if dupes:
                raise ValidationError(_(
                    "Vehicle '%s' already has an active driver assignment. "
                    "Set a return date on the previous assignment first."
                ) % (rec.vehicle_id.license_plate or rec.vehicle_id.name))

    @api.constrains('handover_date', 'return_date')
    def _check_dates(self):
        for rec in self:
            if rec.return_date and rec.handover_date and rec.return_date < rec.handover_date:
                raise ValidationError(_("Return date cannot be before handover date."))

    def action_mark_returned(self):
        for rec in self:
            if not rec.return_date:
                rec.return_date = fields.Date.context_today(self)
