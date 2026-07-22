# -*- coding: utf-8 -*-
"""CR3-FINAL Part D — cumulative / multi-month statement.

One record = one month, so there was no way to produce a statement spanning a
quarter or a year; each month had to be printed on its own.

This wizard aggregates the SAME figures the contract dashboard already holds —
it never recalculates them. Each month row reads the stored values off the
contract, so a month in this report always equals that contract's own screen.
Only the TOTAL row does arithmetic, and it recalculates the percentages from
the summed amounts rather than adding percentages together.
"""
import base64
import io
from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# (field, label, kind) — kind 'amount' sums; kind 'pct' recalculates from
# (numerator, denominator) at the total level.
BILLING_SUMMARY = [
    ('bs_total_invoiced', 'Project Income'),
    ('bs_total_project_cgs', 'Direct Cost (COGS)'),
    ('bs_total_project_exp', 'Operating Expenses'),
    ('bs_total_project_exp_all', 'Total Project Exp'),
    ('bs_total_budget_cost', 'Budgeted Cost'),
    ('bs_total_actual_cost', 'Actual Cost'),
    ('bs_remaining_budget', 'Remaining Budget'),
    ('bs_budget_variance', 'Budget Variance'),
    ('bs_sales_person_commission', 'Salesperson Commission'),
]
PROFITABILITY = [
    ('pp_gross_profit', 'Gross Profit'),
    ('pp_net_profit', 'Net Profit'),
    ('pp_budgeted_profit', 'Profit After Budget'),
    ('pp_actual_profit', 'Profit After Actual Cost'),
    ('pp_profit_after_commission', 'Net Profit After Commission'),
]
# KPI% → (numerator field, denominator field) so the TOTAL row is recalculated.
KPIS = [
    ('kpi_gross_margin', 'Gross Margin %', 'pp_gross_profit', 'bs_total_invoiced'),
    ('kpi_net_margin', 'Net Margin %', 'pp_net_profit', 'bs_total_invoiced'),
    ('kpi_cogs_pct', 'COGS %', 'bs_total_project_cgs', 'bs_total_invoiced'),
    ('kpi_opex_pct', 'Operating Expense %', 'bs_total_project_exp', 'bs_total_invoiced'),
    ('kpi_total_cost_pct', 'Total Cost %', 'bs_total_project_exp_all', 'bs_total_invoiced'),
    ('kpi_roc', 'Profit to Cost (ROC) %', 'pp_net_profit', 'bs_total_project_exp_all'),
    ('kpi_budget_variance_pct', 'Budget Variance %', 'bs_budget_variance', 'bs_total_budget_cost'),
    ('kpi_budget_usage_pct', 'Budget Usage %', 'bs_total_actual_cost', 'bs_total_budget_cost'),
    ('kpi_net_return_on_cost_after_commission', 'Net Return on Cost After Commission %',
     'pp_profit_after_commission', 'bs_total_project_exp_all'),
]


class Way4TechManpowerCumulativeWizard(models.TransientModel):
    _name = 'way4tech.manpower.cumulative.wizard'
    _description = 'Manpower — Cumulative Statement'

    client_id = fields.Many2one(
        'res.partner', string='Client',
        help='Leave empty for all clients.',
    )
    project_id = fields.Many2one(
        'way4tech.project', string='Project',
        help='Leave empty for all projects.',
    )
    salesperson_id = fields.Many2one(
        'hr.employee', string='Salesperson',
        help='Leave empty for all salespeople.',
    )
    period = fields.Selection(
        selection=[
            ('this_month', 'This Month'),
            ('last_month', 'Last Month'),
            ('this_quarter', 'This Quarter'),
            ('this_year', 'This Year'),
            ('custom', 'Custom Range'),
        ],
        default='this_year', required=True,
    )
    date_from = fields.Date(string='From', compute='_compute_dates',
                            store=True, readonly=False)
    date_to = fields.Date(string='To', compute='_compute_dates',
                          store=True, readonly=False)
    xlsx_file = fields.Binary(string='XLSX', readonly=True)
    xlsx_name = fields.Char(string='File Name', readonly=True)

    @api.depends('period')
    def _compute_dates(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if rec.period == 'this_month':
                rec.date_from = today.replace(day=1)
                rec.date_to = self._month_end(today)
            elif rec.period == 'last_month':
                first = today.replace(day=1)
                prev = fields.Date.add(first, days=-1)
                rec.date_from = prev.replace(day=1)
                rec.date_to = prev
            elif rec.period == 'this_quarter':
                q_start_month = 3 * ((today.month - 1) // 3) + 1
                rec.date_from = today.replace(month=q_start_month, day=1)
                end_month = q_start_month + 2
                rec.date_to = self._month_end(today.replace(month=end_month, day=1))
            elif rec.period == 'this_year':
                rec.date_from = today.replace(month=1, day=1)
                rec.date_to = today.replace(month=12, day=31)
            # 'custom' leaves whatever the user typed.

    @staticmethod
    def _month_end(day):
        if day.month == 12:
            return day.replace(year=day.year + 1, month=1, day=1) - \
                (date(2000, 1, 2) - date(2000, 1, 1))
        return day.replace(month=day.month + 1, day=1) - \
            (date(2000, 1, 2) - date(2000, 1, 1))

    # ── Data ──────────────────────────────────────────────────────────────
    def _get_contracts(self):
        self.ensure_one()
        if not self.date_from or not self.date_to:
            raise UserError(_('Pick a period first.'))
        domain = [
            ('start_date', '>=', self.date_from),
            ('start_date', '<=', self.date_to),
            ('state', '!=', 'cancelled'),
        ]
        if self.client_id:
            domain.append(('client_id', '=', self.client_id.id))
        if self.project_id:
            domain.append(('way4tech_project_id', '=', self.project_id.id))
        if self.salesperson_id:
            domain.append(('salesperson_id', '=', self.salesperson_id.id))
        return self.env['way4tech.manpower.contract'].search(
            domain, order='client_id, way4tech_project_id, start_date',
        )

    def _build_data(self):
        """Group → months → figures, plus a recalculated grand total."""
        self.ensure_one()
        contracts = self._get_contracts()
        groups = {}
        for c in contracts:
            key = (c.client_id.id, c.way4tech_project_id.id)
            grp = groups.setdefault(key, {
                'client': c.client_id.display_name or '',
                'project': c.way4tech_project_id.display_name or '',
                'months': [],
            })
            row = {'month': c.start_date.strftime('%m/%Y') if c.start_date else '',
                   'contract': c.display_name}
            for fname, _label in BILLING_SUMMARY + PROFITABILITY:
                row[fname] = c[fname]
            for fname, _label, _n, _d in KPIS:
                row[fname] = c[fname]
            grp['months'].append(row)

        def totals_of(rows):
            tot = {}
            for fname, _label in BILLING_SUMMARY + PROFITABILITY:
                tot[fname] = sum(r[fname] for r in rows)
            # Percentages RECALCULATED from the totals, never summed.
            for fname, _label, num, den in KPIS:
                d = tot.get(den) or 0.0
                tot[fname] = (tot.get(num, 0.0) / d * 100.0) if d else 0.0
            return tot

        for grp in groups.values():
            grp['total'] = totals_of(grp['months'])
        all_rows = [r for g in groups.values() for r in g['months']]
        return {
            'groups': list(groups.values()),
            'grand_total': totals_of(all_rows) if all_rows else {},
            'billing_summary': BILLING_SUMMARY,
            'profitability': PROFITABILITY,
            'kpis': [(f, l) for f, l, _n, _d in KPIS],
            'date_from': self.date_from,
            'date_to': self.date_to,
            'filters': ' · '.join(p for p in (
                self.client_id.display_name or '',
                self.project_id.display_name or '',
                self.salesperson_id.display_name or '',
            ) if p) or _('All clients, projects and salespeople'),
            'contract_count': len(contracts),
            'currency': self.env.company.currency_id,
        }

    # ── Outputs ───────────────────────────────────────────────────────────
    def action_print_pdf(self):
        self.ensure_one()
        data = self._build_data()
        if not data['groups']:
            raise UserError(_('No contracts match those filters.'))
        return self.env.ref(
            'way4tech_logistics.action_report_manpower_cumulative',
        ).report_action(self, data={'wizard_id': self.id})

    def action_export_xlsx(self):
        """Same figures, as a spreadsheet."""
        self.ensure_one()
        try:
            import xlsxwriter
        except ImportError:
            raise UserError(_(
                'The xlsxwriter Python library is not available on this '
                'server, so XLSX export cannot run. Use Print PDF instead, '
                'or ask your administrator to install xlsxwriter.'
            ))
        data = self._build_data()
        if not data['groups']:
            raise UserError(_('No contracts match those filters.'))

        stream = io.BytesIO()
        book = xlsxwriter.Workbook(stream, {'in_memory': True})
        f_title = book.add_format({'bold': True, 'font_size': 14})
        f_hdr = book.add_format({'bold': True, 'bg_color': '#003366',
                                 'font_color': '#FFFFFF', 'border': 1})
        f_grp = book.add_format({'bold': True, 'bg_color': '#DDE6F0'})
        f_num = book.add_format({'num_format': '#,##0.00', 'border': 1})
        f_pct = book.add_format({'num_format': '#,##0.00"%"', 'border': 1})
        f_tot = book.add_format({'bold': True, 'num_format': '#,##0.00',
                                 'top': 2, 'border': 1})
        f_totp = book.add_format({'bold': True, 'num_format': '#,##0.00"%"',
                                  'top': 2, 'border': 1})
        sheet = book.add_worksheet('Cumulative Statement')
        sheet.set_column(0, 0, 30)
        sheet.set_column(1, 40, 16)

        sheet.write(0, 0, 'Manpower Cumulative Statement', f_title)
        sheet.write(1, 0, 'Period: %s to %s' % (data['date_from'], data['date_to']))
        sheet.write(2, 0, 'Filters: %s' % data['filters'])
        row = 4

        columns = ([(f, l) for f, l in data['billing_summary']]
                   + [(f, l) for f, l in data['profitability']]
                   + list(data['kpis']))
        pct_fields = {f for f, _l in data['kpis']}

        for grp in data['groups']:
            label = ' — '.join(p for p in (grp['client'], grp['project']) if p)
            sheet.write(row, 0, label or 'Unassigned', f_grp)
            row += 1
            sheet.write(row, 0, 'Month', f_hdr)
            for idx, (_f, lbl) in enumerate(columns, start=1):
                sheet.write(row, idx, lbl, f_hdr)
            row += 1
            for m in grp['months']:
                sheet.write(row, 0, m['month'])
                for idx, (fname, _lbl) in enumerate(columns, start=1):
                    fmt = f_pct if fname in pct_fields else f_num
                    sheet.write_number(row, idx, m.get(fname) or 0.0, fmt)
                row += 1
            sheet.write(row, 0, 'TOTAL', f_grp)
            for idx, (fname, _lbl) in enumerate(columns, start=1):
                fmt = f_totp if fname in pct_fields else f_tot
                sheet.write_number(row, idx, grp['total'].get(fname) or 0.0, fmt)
            row += 3

        if len(data['groups']) > 1:
            sheet.write(row, 0, 'GRAND TOTAL', f_grp)
            for idx, (fname, _lbl) in enumerate(columns, start=1):
                fmt = f_totp if fname in pct_fields else f_tot
                sheet.write_number(row, idx,
                                   data['grand_total'].get(fname) or 0.0, fmt)

        book.close()
        stream.seek(0)
        self.write({
            'xlsx_file': base64.b64encode(stream.read()),
            'xlsx_name': 'Cumulative_Statement_%s_%s.xlsx' % (
                data['date_from'], data['date_to']),
        })
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/?model=%s&id=%s&field=xlsx_file'
                   '&filename_field=xlsx_name&download=true' % (self._name, self.id),
            'target': 'self',
        }
