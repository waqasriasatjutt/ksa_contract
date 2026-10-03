from datetime import date

from odoo import fields, models, _
from odoo.exceptions import UserError


class TruckProfitabilityWizard(models.TransientModel):
    """
    Wizard for generating Truck-wise and Customer-wise profitability PDF reports.
    The user selects a date range, grouping dimension (truck / client), and optional
    filters, then clicks Print Report to get a QWeb PDF.
    """
    _name = 'way4tech.truck.profitability.wizard'
    _description = 'Truck / Client Profitability Report'

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
    report_type = fields.Selection(
        selection=[
            ('truck', 'Truck-wise Profitability'),
            ('client', 'Customer-wise Profitability'),
        ],
        string='Group By',
        default='truck',
        required=True,
    )
    state_filter = fields.Selection(
        selection=[
            ('all', 'All Statuses'),
            ('confirmed', 'Confirmed Only'),
            ('done', 'Done Only'),
            ('confirmed_done', 'Confirmed & Done'),
        ],
        string='Trip Status',
        default='confirmed_done',
        required=True,
    )
    truck_ids = fields.Many2many(
        comodel_name='fleet.vehicle',
        string='Filter by Trucks',
        help='Leave empty to include all trucks.',
    )
    client_ids = fields.Many2many(
        comodel_name='res.partner',
        string='Filter by Clients',
        help='Leave empty to include all clients.',
    )
    include_maintenance = fields.Boolean(
        string='Include Maintenance Cost',
        default=True,
        help='Counts the maintenance logged against each truck in the period as '
             'a cost, so the profit is after maintenance. Every log is listed as '
             'its own line. Untick to report trip costs only.',
    )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _build_domain(self):
        domain = [
            ('trip_date', '>=', self.date_from),
            ('trip_date', '<=', self.date_to),
            ('company_id', '=', self.env.company.id),
        ]
        if self.state_filter == 'confirmed':
            domain.append(('state', '=', 'confirmed'))
        elif self.state_filter == 'done':
            domain.append(('state', '=', 'done'))
        elif self.state_filter == 'confirmed_done':
            domain.append(('state', 'in', ['confirmed', 'done']))
        if self.truck_ids:
            domain.append(('truck_id', 'in', self.truck_ids.ids))
        if self.client_ids:
            domain.append(('client_id', 'in', self.client_ids.ids))
        return domain

    def _maintenance_domain(self):
        """Maintenance logged in the period, for the trucks in scope."""
        domain = [
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('company_id', '=', self.env.company.id),
            ('amount', '!=', 0),
        ]
        if self.truck_ids:
            domain.append(('vehicle_id', 'in', self.truck_ids.ids))
        return domain

    def get_report_rows(self):
        """Every entry in the period as its own row, grouped by truck or client.

        One row per trip and one row per maintenance log, so ten maintenance
        logs read as ten lines. Profit on a row is its revenue less its driver,
        fuel, other and maintenance cost, and a group's totals are the sum of
        its rows.
        """
        self.ensure_one()
        trips = self.env['way4tech.truck.trip'].search(
            self._build_domain(), order='trip_date asc, id asc')
        logs = self.env['fleet.vehicle.log.services']
        if self.include_maintenance:
            logs = logs.search(self._maintenance_domain(), order='date asc, id asc')

        trip_types = dict(
            self.env['way4tech.truck.trip']._fields['trip_type'].selection or [])
        buckets = {}

        def bucket(key, label, sub_label):
            if key not in buckets:
                buckets[key] = {
                    'label': label or _('(Unassigned)'),
                    'sub_label': sub_label or '',
                    'rows': [],
                }
            return buckets[key]

        for trip in trips:
            if self.report_type == 'truck':
                key = ('truck', trip.truck_id.id)
                holder = bucket(key, trip.truck_id.name,
                                trip.truck_id.license_plate)
            else:
                key = ('client', trip.client_id.id)
                holder = bucket(key, trip.client_id.name,
                                trip.client_id.commercial_company_name)
            # Other Cost carries the trip's own other costs and, on a middleman
            # trip, the third-party hire. Left out of the profit, those costs
            # would simply disappear from the report.
            other = trip.other_cost_total - trip.fuel_cost
            holder['rows'].append({
                'date': trip.trip_date,
                'reference': trip.name or '',
                'truck': trip.truck_id.name or '',
                'client': trip.client_id.name or '',
                'kind': trip_types.get(trip.trip_type, trip.trip_type or ''),
                'revenue': trip.revenue,
                'driver': trip.driver_cost,
                'fuel': trip.fuel_cost,
                'other': other,
                'maintenance': 0.0,
            })

        for log in logs:
            if self.report_type == 'truck':
                key = ('truck', log.vehicle_id.id)
                holder = bucket(key, log.vehicle_id.name,
                                log.vehicle_id.license_plate)
            else:
                # Maintenance belongs to a truck, not to a customer, so it sits
                # in its own group and the grand total still ties.
                key = ('client', 0)
                holder = bucket(key, _('Vehicle Maintenance'), '')
            holder['rows'].append({
                'date': log.date,
                'reference': log.way4tech_ref or '',
                'truck': log.vehicle_id.name or '',
                'client': '',
                'kind': _('Maintenance'),
                'revenue': 0.0,
                'driver': 0.0,
                'fuel': 0.0,
                'other': 0.0,
                'maintenance': log.amount,
            })

        groups = []
        for holder in buckets.values():
            rows = sorted(holder['rows'], key=lambda r: (r['date'] or date.min,
                                                         r['reference']))
            for row in rows:
                row['cost'] = row['driver'] + row['fuel'] + row['other'] + row['maintenance']
                row['profit'] = row['revenue'] - row['cost']
                row['margin'] = (row['profit'] / row['revenue'] * 100.0
                                 if row['revenue'] else 0.0)
            holder['rows'] = rows
            holder['totals'] = self._sum_rows(rows)
            groups.append(holder)
        groups.sort(key=lambda g: g['label'])
        return {
            'groups': groups,
            'totals': self._sum_rows([r for g in groups for r in g['rows']]),
        }

    def _sum_rows(self, rows):
        totals = {'count': len(rows)}
        for key in ('revenue', 'driver', 'fuel', 'other', 'maintenance',
                    'cost', 'profit'):
            totals[key] = sum(row.get(key, 0.0) for row in rows)
        totals['margin'] = (totals['profit'] / totals['revenue'] * 100.0
                            if totals['revenue'] else 0.0)
        return totals

    # ── actions ───────────────────────────────────────────────────────────────

    def action_print_report(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('From Date must be on or before To Date.'))
        if self.report_type == 'truck':
            ref = 'way4tech_logistics.action_report_truck_profitability'
        else:
            ref = 'way4tech_logistics.action_report_client_profitability'
        return self.env.ref(ref).report_action(self)
