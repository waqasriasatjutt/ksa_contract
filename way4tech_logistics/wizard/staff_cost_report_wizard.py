from odoo import api, fields, models, _


class Way4TechStaffCostReportWizard(models.TransientModel):
    """
    Office Staff Full Cost Report.
    Shows per-employee breakdown:
      Salary + GOSI + Iqama + Insurance + Saudization + Other Compliance
    Aggregates from way4tech.employee.cost records.
    """
    _name = 'way4tech.staff.cost.report.wizard'
    _description = 'Office Staff Cost Report Wizard'

    date_from = fields.Date(
        string='From', required=True,
        default=lambda self: fields.Date.today().replace(day=1),
    )
    date_to = fields.Date(
        string='To', required=True,
        default=fields.Date.today,
    )
    employee_ids = fields.Many2many(
        'hr.employee', string='Employees',
        help='Leave empty to include all employees with compliance cost records.',
    )
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company,
    )

    # ── Data ──────────────────────────────────────────────────────────────────

    def get_data(self):
        """
        Return (rows, grand_totals) where each row is a dict with:
          employee, salary, gosi, iqama, insurance, saudization, other, total
        """
        domain = [
            ('period_start', '>=', self.date_from),
            ('period_end', '<=', self.date_to),
        ]
        if self.company_id:
            domain += [('company_id', '=', self.company_id.id)]
        if self.employee_ids:
            domain += [('employee_id', 'in', self.employee_ids.ids)]

        costs = self.env['way4tech.employee.cost'].search(domain)
        result = {}
        for c in costs:
            eid = c.employee_id.id
            if eid not in result:
                result[eid] = {
                    'employee': c.employee_id.name,
                    'job': c.employee_id.job_title or '',
                    'salary': 0.0, 'gosi': 0.0, 'iqama': 0.0,
                    'insurance': 0.0, 'saudization': 0.0,
                    'other': 0.0, 'total': 0.0,
                }
            result[eid]['salary'] += c.basic_salary
            result[eid]['gosi'] += c.gosi_amount
            result[eid]['iqama'] += c.iqama_amount
            result[eid]['insurance'] += c.insurance_amount
            result[eid]['saudization'] += c.saudization_amount
            result[eid]['other'] += c.other_costs
            result[eid]['total'] += c.total_cost

        rows = sorted(result.values(), key=lambda r: r['employee'])
        keys = ('salary', 'gosi', 'iqama', 'insurance', 'saudization', 'other', 'total')
        grand = {k: sum(r[k] for r in rows) for k in keys}
        grand['employee'] = 'Grand Total'
        grand['job'] = ''
        return rows, grand

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_print_report(self):
        return self.env.ref(
            'way4tech_logistics.action_report_staff_cost'
        ).report_action(self)
