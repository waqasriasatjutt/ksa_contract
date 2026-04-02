from collections import defaultdict
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class MaintenanceHistoryWizard(models.TransientModel):
    """
    Wizard for generating a Maintenance History PDF report per truck.
    Reads from fleet.vehicle.log.services (extended with way4tech fields).
    Detects repeated repairs: same maintenance category on the same vehicle
    occurring more than once within the selected period.
    """
    _name = 'way4tech.maintenance.history.wizard'
    _description = 'Maintenance History Report'

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
    vehicle_ids = fields.Many2many(
        comodel_name='fleet.vehicle',
        string='Filter by Trucks',
        help='Leave empty to include all trucks.',
    )
    maint_type_filter = fields.Selection(
        selection=[
            ('all', 'All Categories'),
            ('preventive', 'Preventive'),
            ('corrective', 'Corrective'),
            ('accident', 'Accident Repair'),
            ('tyres', 'Tyres'),
            ('other', 'Other'),
        ],
        string='Category Filter',
        default='all',
        required=True,
    )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _build_domain(self):
        domain = [
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('company_id', '=', self.env.company.id),
        ]
        if self.vehicle_ids:
            domain.append(('vehicle_id', 'in', self.vehicle_ids.ids))
        if self.maint_type_filter and self.maint_type_filter != 'all':
            domain.append(('way4tech_maint_type', '=', self.maint_type_filter))
        return domain

    def get_grouped_data(self):
        """
        Returns a list of dicts, one per vehicle, sorted by vehicle name:
          {
            'vehicle_name': str,
            'license_plate': str,
            'records': recordset,        # fleet.vehicle.log.services
            'record_count': int,
            'total_cost': float,
            'repeat_types': list[str],   # maint categories with > 1 occurrence
          }
        """
        self.ensure_one()
        records = self.env['fleet.vehicle.log.services'].search(
            self._build_domain(), order='date asc'
        )

        buckets = defaultdict(lambda: {
            'records': self.env['fleet.vehicle.log.services'],
            'total_cost': 0.0,
            'type_counts': defaultdict(int),
        })

        for rec in records:
            vid = rec.vehicle_id.id
            b = buckets[vid]
            b['records'] |= rec
            b['total_cost'] += rec.amount or 0.0
            b['type_counts'][rec.way4tech_maint_type or 'other'] += 1

        # Build label map for maint types
        maint_labels = dict(
            self.env['fleet.vehicle.log.services'].fields_get(
                ['way4tech_maint_type']
            )['way4tech_maint_type']['selection']
        )

        result = []
        for vid, data in buckets.items():
            vehicle = self.env['fleet.vehicle'].browse(vid)
            repeat_types = [
                maint_labels.get(t, t)
                for t, cnt in data['type_counts'].items()
                if cnt > 1
            ]
            result.append({
                'vehicle_name': vehicle.name or _('(Unknown Truck)'),
                'license_plate': vehicle.license_plate or '',
                'records': data['records'].sorted(key=lambda r: r.date),
                'record_count': len(data['records']),
                'total_cost': data['total_cost'],
                'repeat_types': repeat_types,
            })

        result.sort(key=lambda r: r['vehicle_name'])
        return result

    def get_grand_totals(self):
        """Grand-total dict for the report footer."""
        self.ensure_one()
        rows = self.get_grouped_data()
        return {
            'vehicle_count': len(rows),
            'record_count': sum(r['record_count'] for r in rows),
            'total_cost': sum(r['total_cost'] for r in rows),
        }

    # ── actions ───────────────────────────────────────────────────────────────

    def action_print_report(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('From Date must be on or before To Date.'))
        return self.env.ref(
            'way4tech_logistics.action_report_maintenance_history'
        ).report_action(self)
