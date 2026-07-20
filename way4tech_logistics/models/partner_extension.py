from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # KSA business identifiers
    way4tech_cr_number = fields.Char(
        string='CR #',
        help='Commercial Registration number (companies only).',
    )
    way4tech_iqama_number = fields.Char(
        string='Iqama #',
        help='KSA residency permit number (individuals only).',
    )


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    way4tech_iqama_number = fields.Char(
        string='Iqama #',
        groups='hr.group_hr_user',
        help='KSA residency permit number for drivers, riders and staff.',
    )
    # CR3 P3 (v13.0): Per Day Allowed Hours — EMPLOYEE master.
    # Priority chain in timesheet.per_day_hours default:
    #   contract.default_per_day_allowed_hours (if set)
    #   → employee.default_per_day_allowed_hours (fallback)
    #   → line-level manual override (always wins for the specific row).
    default_per_day_allowed_hours = fields.Float(
        string='Default Per Day Allowed Hours',
        digits=(16, 2),
        groups='hr.group_hr_user',
        help='Default per-day allowed hours for this employee. Used as '
             'fallback when a timesheet row picks this employee AND the '
             'contract has no per-day default set. Line-level override '
             'always wins.',
    )
