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

    def _way4tech_ensure_active_receivable(self, company):
        """Receivable twin of the Item 7 payable fallback (manpower_contract.
        _way4tech_ensure_active_payable): an archived/inactive default
        receivable must never block a CUSTOMER invoice from posting. If the
        account this customer would post its receivable to (its own property,
        or the company default it inherits) is archived, point the customer at
        the company's first ACTIVE receivable so the invoice posts to a real
        account.

        Durable + general: fires for ANY company/customer whose default
        receivable happens to be archived (the client archives their own
        defaults as normal usage), never a one-off for a single code. Safe by
        construction — it only ever REPLACES an inactive account with an active
        one of the SAME type (asset_receivable), touches no invoice posting
        logic and no core Accounting, and leaves an already-active receivable
        exactly as it is (returns immediately)."""
        self.ensure_one()
        if not company:
            return
        current = self.with_company(company).property_account_receivable_id
        if current and current.active:
            return  # already valid — never touch a working setup
        active = self.env['account.account'].search([
            ('account_type', '=', 'asset_receivable'),
            ('company_ids', 'in', company.id),
            ('active', '=', True),
        ], limit=1)
        if active:
            self.with_company(company).property_account_receivable_id = active


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
