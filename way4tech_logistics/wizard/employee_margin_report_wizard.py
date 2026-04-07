from odoo import api, fields, models, _


class Way4TechEmployeeMarginReportWizard(models.TransientModel):
    """
    Rider / Driver Profitability (Margin) Report.
    Revenue: truck trip revenue attributed to driver + manpower contract revenue.
    Cost:    salary import net payable + KSA compliance costs.
    Margin = Revenue − Total Cost
    """
    _name = 'way4tech.employee.margin.report.wizard'
    _description = 'Rider / Driver Margin Report Wizard'

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
        help='Leave empty for all employees with trip or salary records.',
    )
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company,
    )

    # ── Data ──────────────────────────────────────────────────────────────────

    def get_data(self):
        """
        Return (rows, grand_totals).
        Each row: employee, revenue, salary_cost, compliance_cost, total_cost, margin, margin_pct
        """
        emp_filter = self.employee_ids.ids if self.employee_ids else None
        company_id = self.company_id.id if self.company_id else None
        result = {}

        def _row(employee):
            return {
                'employee': employee.name,
                'job': employee.job_title or '',
                'revenue': 0.0,
                'salary_cost': 0.0,
                'compliance_cost': 0.0,
                'total_cost': 0.0,
                'margin': 0.0,
                'margin_pct': 0.0,
            }

        # ── Salary costs (from import lines) ─────────────────────────────────
        sal_domain = [
            ('import_id.period_start', '>=', self.date_from),
            ('import_id.period_end', '<=', self.date_to),
            ('import_id.state', 'in', ('imported', 'done')),
            ('employee_id', '!=', False),
        ]
        if company_id:
            sal_domain += [('import_id.company_id', '=', company_id)]
        if emp_filter:
            sal_domain += [('employee_id', 'in', emp_filter)]
        for line in self.env['way4tech.salary.import.line'].search(sal_domain):
            eid = line.employee_id.id
            if eid not in result:
                result[eid] = _row(line.employee_id)
            result[eid]['salary_cost'] += line.net_payable

        # ── Revenue from truck trips (driver) ─────────────────────────────────
        trip_domain = [
            ('trip_date', '>=', self.date_from),
            ('trip_date', '<=', self.date_to),
            ('state', 'in', ('confirmed', 'done')),
            ('driver_id', '!=', False),
        ]
        if company_id:
            trip_domain += [('company_id', '=', company_id)]
        if emp_filter:
            trip_domain += [('driver_id', 'in', emp_filter)]
        for trip in self.env['way4tech.truck.trip'].search(trip_domain):
            eid = trip.driver_id.id
            if eid not in result:
                result[eid] = _row(trip.driver_id)
            result[eid]['revenue'] += trip.revenue

        # ── KSA compliance costs ──────────────────────────────────────────────
        comp_domain = [
            ('period_start', '>=', self.date_from),
            ('period_end', '<=', self.date_to),
            ('employee_id', '!=', False),
        ]
        if company_id:
            comp_domain += [('company_id', '=', company_id)]
        if emp_filter:
            comp_domain += [('employee_id', 'in', emp_filter)]
        for c in self.env['way4tech.employee.cost'].search(comp_domain):
            eid = c.employee_id.id
            if eid in result:
                result[eid]['compliance_cost'] += c.total_cost

        # ── Totals & margin ───────────────────────────────────────────────────
        for row in result.values():
            row['total_cost'] = row['salary_cost'] + row['compliance_cost']
            row['margin'] = row['revenue'] - row['total_cost']
            row['margin_pct'] = (
                (row['margin'] / row['revenue'] * 100.0) if row['revenue'] else 0.0
            )

        rows = sorted(result.values(), key=lambda r: r['employee'])
        keys = ('revenue', 'salary_cost', 'compliance_cost', 'total_cost', 'margin')
        grand = {k: sum(r[k] for r in rows) for k in keys}
        grand['employee'] = 'Grand Total'
        grand['job'] = ''
        grand['margin_pct'] = (
            (grand['margin'] / grand['revenue'] * 100.0) if grand['revenue'] else 0.0
        )
        return rows, grand

    def action_print_report(self):
        return self.env.ref(
            'way4tech_logistics.action_report_employee_margin'
        ).report_action(self)
