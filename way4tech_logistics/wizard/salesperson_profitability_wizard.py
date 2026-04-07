from collections import defaultdict
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SalespersonProfitabilityWizard(models.TransientModel):
    """
    Wizard for generating Salesperson Profitability PDF report.
    Aggregates truck trips (revenue/cost/profit) and manpower contracts
    (invoiced/expenses/margin) by salesperson for the selected date range.
    """
    _name = 'way4tech.salesperson.profitability.wizard'
    _description = 'Salesperson Profitability Report'

    date_from = fields.Date(
        string='From Date',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
    )
    date_to = fields.Date(
        string='To Date',
        required=True,
        default=fields.Date.today,
    )
    salesperson_ids = fields.Many2many(
        comodel_name='res.users',
        string='Filter by Salesperson',
        help='Leave empty to include all salespersons.',
    )

    # ── helpers ───────────────────────────────────────────────────────────────

    def get_report_data(self):
        """
        Returns a list of dicts, one per salesperson, containing:
          - Truck trips: revenue, cost, gross_profit, trip_count
          - Manpower contracts: total_invoiced, total_expenses, margin
          - Combined totals
        """
        self.ensure_one()
        company_id = self.env.company.id

        # --- Truck Trips ---
        trip_domain = [
            ('trip_date', '>=', self.date_from),
            ('trip_date', '<=', self.date_to),
            ('state', 'in', ['confirmed', 'done']),
            ('company_id', '=', company_id),
        ]
        if self.salesperson_ids:
            trip_domain.append(('salesperson_id', 'in', self.salesperson_ids.ids))

        trips = self.env['way4tech.truck.trip'].search(trip_domain, order='trip_date asc')

        trip_buckets = defaultdict(lambda: {
            'trips': self.env['way4tech.truck.trip'],
            'revenue': 0.0,
            'cost': 0.0,
            'gross_profit': 0.0,
        })
        for trip in trips:
            uid = trip.salesperson_id.id or 0
            b = trip_buckets[uid]
            b['trips'] |= trip
            b['revenue'] += trip.revenue
            b['cost'] += trip.total_cost
            b['gross_profit'] += trip.gross_profit

        # --- Manpower Contracts ---
        contract_domain = [
            ('start_date', '<=', self.date_to),
            ('state', 'in', ['active', 'completed']),
            ('company_id', '=', company_id),
        ]
        if self.salesperson_ids:
            contract_domain.append(('salesperson_id', 'in', self.salesperson_ids.ids))

        contracts = self.env['way4tech.manpower.contract'].search(contract_domain)

        contract_buckets = defaultdict(lambda: {
            'contracts': self.env['way4tech.manpower.contract'],
            'total_invoiced': 0.0,
            'total_expenses': 0.0,
            'margin': 0.0,
        })
        for c in contracts:
            uid = c.salesperson_id.id or 0
            b = contract_buckets[uid]
            b['contracts'] |= c
            b['total_invoiced'] += c.total_invoiced
            b['total_expenses'] += c.total_project_expenses
            b['margin'] += c.project_margin

        # --- Merge all salesperson IDs ---
        all_uids = set(trip_buckets.keys()) | set(contract_buckets.keys())

        result = []
        for uid in all_uids:
            if uid:
                user = self.env['res.users'].browse(uid)
                name = user.name or _('(Unknown)')
            else:
                name = _('(No Salesperson)')

            td = trip_buckets.get(uid, {'trips': self.env['way4tech.truck.trip'], 'revenue': 0.0, 'cost': 0.0, 'gross_profit': 0.0})
            cd = contract_buckets.get(uid, {'contracts': self.env['way4tech.manpower.contract'], 'total_invoiced': 0.0, 'total_expenses': 0.0, 'margin': 0.0})

            trip_rev = td['revenue']
            trip_margin_pct = (td['gross_profit'] / trip_rev * 100.0) if trip_rev else 0.0

            result.append({
                'salesperson_name': name,
                # trips
                'trips': td['trips'].sorted(key=lambda t: t.trip_date),
                'trip_count': len(td['trips']),
                'trip_revenue': trip_rev,
                'trip_cost': td['cost'],
                'trip_profit': td['gross_profit'],
                'trip_margin_pct': trip_margin_pct,
                # contracts
                'contracts': cd['contracts'],
                'contract_count': len(cd['contracts']),
                'contract_invoiced': cd['total_invoiced'],
                'contract_expenses': cd['total_expenses'],
                'contract_margin': cd['margin'],
            })

        result.sort(key=lambda r: r['salesperson_name'])
        return result

    def get_grand_totals(self):
        """Grand-total dict for the report footer."""
        self.ensure_one()
        rows = self.get_report_data()
        trip_rev = sum(r['trip_revenue'] for r in rows)
        trip_cost = sum(r['trip_cost'] for r in rows)
        trip_profit = sum(r['trip_profit'] for r in rows)
        trip_margin = (trip_profit / trip_rev * 100.0) if trip_rev else 0.0
        contract_inv = sum(r['contract_invoiced'] for r in rows)
        contract_exp = sum(r['contract_expenses'] for r in rows)
        contract_margin = sum(r['contract_margin'] for r in rows)
        return {
            'trip_count': sum(r['trip_count'] for r in rows),
            'trip_revenue': trip_rev,
            'trip_cost': trip_cost,
            'trip_profit': trip_profit,
            'trip_margin_pct': trip_margin,
            'contract_count': sum(r['contract_count'] for r in rows),
            'contract_invoiced': contract_inv,
            'contract_expenses': contract_exp,
            'contract_margin': contract_margin,
        }

    # ── actions ───────────────────────────────────────────────────────────────

    def action_print_report(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('From Date must be on or before To Date.'))
        return self.env.ref(
            'way4tech_logistics.action_report_salesperson_profitability'
        ).report_action(self)
