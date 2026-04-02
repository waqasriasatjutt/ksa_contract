from collections import defaultdict
from odoo import api, fields, models, _
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

    def get_grouped_data(self):
        """
        Called from the QWeb template to get grouped/aggregated trip data.
        Returns a list of dicts sorted by group name:
          [{
              'label': str,            # truck name or client name
              'trips': recordset,      # way4tech.truck.trip
              'trip_count': int,
              'total_revenue': float,
              'total_cost': float,
              'total_profit': float,
              'margin_pct': float,     # % profit margin
          }, ...]
        """
        self.ensure_one()
        trips = self.env['way4tech.truck.trip'].search(
            self._build_domain(), order='trip_date asc'
        )

        buckets = defaultdict(lambda: {
            'trips': self.env['way4tech.truck.trip'],
            'total_revenue': 0.0,
            'total_cost': 0.0,
            'total_profit': 0.0,
        })

        for trip in trips:
            key = trip.truck_id.id if self.report_type == 'truck' else trip.client_id.id
            b = buckets[key]
            b['trips'] |= trip
            b['total_revenue'] += trip.revenue
            b['total_cost'] += trip.total_cost
            b['total_profit'] += trip.gross_profit

        result = []
        for key, data in buckets.items():
            if self.report_type == 'truck':
                rec = self.env['fleet.vehicle'].browse(key)
                label = rec.name or _('(No Truck)')
                sub_label = rec.license_plate or ''
            else:
                rec = self.env['res.partner'].browse(key)
                label = rec.name or _('(No Client)')
                sub_label = rec.commercial_company_name or ''

            rev = data['total_revenue']
            margin = (data['total_profit'] / rev * 100.0) if rev else 0.0
            result.append({
                'label': label,
                'sub_label': sub_label,
                'trips': data['trips'].sorted(key=lambda t: t.trip_date),
                'trip_count': len(data['trips']),
                'total_revenue': rev,
                'total_cost': data['total_cost'],
                'total_profit': data['total_profit'],
                'margin_pct': margin,
            })

        result.sort(key=lambda r: r['label'])
        return result

    def get_grand_totals(self):
        """Grand-total row for the report footer."""
        self.ensure_one()
        trips = self.env['way4tech.truck.trip'].search(self._build_domain())
        rev = sum(trips.mapped('revenue'))
        cost = sum(trips.mapped('total_cost'))
        profit = sum(trips.mapped('gross_profit'))
        margin = (profit / rev * 100.0) if rev else 0.0
        return {
            'trip_count': len(trips),
            'total_revenue': rev,
            'total_cost': cost,
            'total_profit': profit,
            'margin_pct': margin,
        }

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
