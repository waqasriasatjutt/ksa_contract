from odoo import api, fields, models, _
from odoo.exceptions import UserError


class InvestorAgingWizard(models.TransientModel):
    """
    Generates an Investor Aging Report showing outstanding (unpaid) investor
    profit-share amounts grouped by investor and aged into 0-30 / 31-60 /
    61-90 / 91+ day buckets from period_end to the chosen as-of date.
    """
    _name = 'way4tech.investor.aging.wizard'
    _description = 'Investor Aging Report'

    as_of_date = fields.Date(
        string='As Of Date',
        required=True,
        default=fields.Date.today,
        help='Aging is calculated from each record\'s Period End to this date.',
    )
    investor_ids = fields.Many2many(
        comodel_name='res.partner',
        string='Filter by Investors',
        help='Leave empty to include all investors.',
    )
    include_draft = fields.Boolean(
        string='Include Draft Records',
        default=True,
        help='Include draft investor payables (not yet confirmed).',
    )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _get_outstanding(self):
        """Return unpaid investor payable records matching the wizard filters."""
        self.ensure_one()
        states = ['confirmed']
        if self.include_draft:
            states.append('draft')
        domain = [
            ('state', 'in', states),
            ('company_id', '=', self.env.company.id),
        ]
        if self.investor_ids:
            domain.append(('investor_id', 'in', self.investor_ids.ids))
        return self.env['way4tech.investor.payable'].search(
            domain, order='investor_id, period_end asc'
        )

    def get_aging_data(self):
        """
        Called from QWeb.  Returns a list (sorted by investor name) of dicts:
        {
            'investor':  res.partner record,
            'records':   [ { record, age_days, bucket, amount }, ... ],
            'current':   float,   # 0–30 days
            'days_31_60': float,
            'days_61_90': float,
            'over_90':   float,
            'total':     float,
            'count':     int,
        }
        """
        self.ensure_one()
        as_of = self.as_of_date
        payables = self._get_outstanding()

        buckets = {}
        for p in payables:
            inv_id = p.investor_id.id or 0
            if inv_id not in buckets:
                buckets[inv_id] = {
                    'investor': p.investor_id,
                    'records': [],
                    'current': 0.0,
                    'days_31_60': 0.0,
                    'days_61_90': 0.0,
                    'over_90': 0.0,
                    'total': 0.0,
                    'count': 0,
                }
            b = buckets[inv_id]
            age = (as_of - p.period_end).days if p.period_end else 0
            amt = p.investor_amount

            if age <= 30:
                b['current'] += amt
                bucket_label = '0–30 days'
            elif age <= 60:
                b['days_31_60'] += amt
                bucket_label = '31–60 days'
            elif age <= 90:
                b['days_61_90'] += amt
                bucket_label = '61–90 days'
            else:
                b['over_90'] += amt
                bucket_label = '91+ days'

            b['total'] += amt
            b['count'] += 1
            b['records'].append({
                'record': p,
                'age_days': age,
                'bucket': bucket_label,
                'amount': amt,
            })

        result = sorted(buckets.values(), key=lambda x: x['investor'].name or '')
        return result

    def get_grand_totals(self):
        """Grand-total row: sum of all aging buckets across all investors."""
        self.ensure_one()
        data = self.get_aging_data()
        return {
            'current': sum(d['current'] for d in data),
            'days_31_60': sum(d['days_31_60'] for d in data),
            'days_61_90': sum(d['days_61_90'] for d in data),
            'over_90': sum(d['over_90'] for d in data),
            'total': sum(d['total'] for d in data),
            'count': sum(d['count'] for d in data),
        }

    # ── action ────────────────────────────────────────────────────────────────

    def action_print_report(self):
        self.ensure_one()
        payables = self._get_outstanding()
        if not payables:
            raise UserError(_(
                'No outstanding investor payables found for the selected criteria.'
            ))
        return self.env.ref(
            'way4tech_logistics.action_report_investor_aging'
        ).report_action(self)
