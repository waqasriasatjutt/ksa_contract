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
