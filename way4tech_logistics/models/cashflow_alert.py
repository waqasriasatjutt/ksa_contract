from odoo import api, fields, models, _
from odoo.exceptions import UserError


class Way4TechCashflowAlertConfig(models.Model):
    """
    Configuration for automatic daily/weekly cash flow email reports.
    One record per company. Sends: bank balances, receivable, payable totals.
    Reports can be triggered manually (button) or by scheduled cron.
    """
    _name = 'way4tech.cashflow.alert.config'
    _description = 'Cash Flow Alert Configuration'
    _rec_name = 'company_id'

    company_id = fields.Many2one(
        'res.company', string='Company',
        required=True, default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)
    recipient_user_ids = fields.Many2many(
        'res.users', string='Recipient Users',
        help='Odoo users who will receive the cash flow email report.',
    )
    extra_emails = fields.Char(
        string='Additional Email(s)',
        help='Comma-separated email addresses outside Odoo (e.g. owner@example.com).',
    )
    frequency = fields.Selection([
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
    ], string='Auto-Send Frequency', default='daily', required=True)
    notes = fields.Text()

    _company_uniq = models.Constraint(
        'UNIQUE(company_id)',
        'Only one Cash Flow Alert configuration per company.',
    )

    def action_send_now(self):
        """Manual trigger: send the report immediately."""
        for config in self:
            config._send_report()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('Cash flow report sent successfully.'),
                'type': 'success',
            },
        }

    def _get_recipients(self):
        """Collect all recipient emails."""
        emails = set()
        for user in self.recipient_user_ids:
            if user.email:
                emails.add(user.email.strip())
        if self.extra_emails:
            for e in self.extra_emails.split(','):
                e = e.strip()
                if e:
                    emails.add(e)
        return emails

    def _send_report(self):
        """Gather financial data and email a formatted cash flow summary."""
        company = self.company_id
        recipients = self._get_recipients()
        if not recipients:
            return

        today = fields.Date.today()
        sym = company.currency_id.symbol or 'SAR'

        # ── Cash & Bank balances ─────────────────────────────────────────────
        cash_journals = self.env['account.journal'].search([
            ('type', 'in', ['bank', 'cash']),
            ('company_id', '=', company.id),
        ])
        balance_rows = ''
        total_liquid = 0.0
        for journal in cash_journals:
            bal = journal.current_statement_balance
            total_liquid += bal
            color = '#198754' if bal >= 0 else '#dc3545'
            balance_rows += (
                f'<tr>'
                f'<td style="padding:6px 12px;">{journal.name}</td>'
                f'<td style="padding:6px 12px;text-align:right;color:{color};">'
                f'{sym} {bal:,.2f}</td>'
                f'</tr>'
            )

        # ── Receivable total ──────────────────────────────────────────────────
        receivable_lines = self.env['account.move.line'].search([
            ('account_id.account_type', '=', 'asset_receivable'),
            ('reconciled', '=', False),
            ('parent_state', '=', 'posted'),
            ('company_id', '=', company.id),
        ])
        total_receivable = sum(receivable_lines.mapped('amount_residual'))

        # ── Payable total ─────────────────────────────────────────────────────
        payable_lines = self.env['account.move.line'].search([
            ('account_id.account_type', '=', 'liability_payable'),
            ('reconciled', '=', False),
            ('parent_state', '=', 'posted'),
            ('company_id', '=', company.id),
        ])
        total_payable = abs(sum(payable_lines.mapped('amount_residual')))

        liq_color = '#198754' if total_liquid >= 0 else '#dc3545'

        body = f'''
        <div style="font-family:Arial,sans-serif;max-width:620px;margin:0 auto;">
          <div style="background:#2c7be5;color:white;padding:16px 20px;border-radius:6px 6px 0 0;">
            <h2 style="margin:0;font-size:18px;">Daily Financial Summary</h2>
            <p style="margin:4px 0 0;opacity:.85;">{company.name} &nbsp;·&nbsp; {today}</p>
          </div>

          <div style="border:1px solid #dee2e6;border-top:none;border-radius:0 0 6px 6px;padding:16px 20px;">

            <h4 style="color:#495057;margin-bottom:8px;">Cash &amp; Bank Balances</h4>
            <table style="width:100%;border-collapse:collapse;margin-bottom:16px;">
              <tr style="background:#f8f9fa;">
                <th style="padding:6px 12px;text-align:left;color:#495057;">Account</th>
                <th style="padding:6px 12px;text-align:right;color:#495057;">Balance</th>
              </tr>
              {balance_rows}
              <tr style="border-top:2px solid #dee2e6;font-weight:bold;">
                <td style="padding:8px 12px;">Total Liquid</td>
                <td style="padding:8px 12px;text-align:right;color:{liq_color};">
                  {sym} {total_liquid:,.2f}</td>
              </tr>
            </table>

            <table style="width:100%;border-collapse:collapse;">
              <tr style="background:#e8f5e9;">
                <td style="padding:10px 14px;font-weight:bold;color:#1b5e20;">
                  Total Receivable (Outstanding)</td>
                <td style="padding:10px 14px;text-align:right;font-weight:bold;
                           color:#1b5e20;font-size:15px;">
                  {sym} {total_receivable:,.2f}</td>
              </tr>
              <tr style="background:#fdecea;">
                <td style="padding:10px 14px;font-weight:bold;color:#b71c1c;">
                  Total Payable (Outstanding)</td>
                <td style="padding:10px 14px;text-align:right;font-weight:bold;
                           color:#b71c1c;font-size:15px;">
                  {sym} {total_payable:,.2f}</td>
              </tr>
              <tr style="background:#fff3e0;">
                <td style="padding:10px 14px;font-weight:bold;color:#e65100;">
                  Net Position (Receivable − Payable)</td>
                <td style="padding:10px 14px;text-align:right;font-weight:bold;
                           color:#e65100;font-size:15px;">
                  {sym} {(total_receivable - total_payable):,.2f}</td>
              </tr>
            </table>

            <p style="margin-top:20px;color:#adb5bd;font-size:11px;">
              Sent automatically by Way4Tech Logistics ERP.<br/>
              To change recipients or schedule: Configuration → Cash Flow Alerts.
            </p>
          </div>
        </div>
        '''

        self.env['mail.mail'].sudo().create({
            'subject': (
                f'[Way4Tech] Financial Summary — {company.name} — {today}'
            ),
            'body_html': body,
            'email_to': ', '.join(recipients),
            'email_from': company.email or 'noreply@way4tech.com',
        }).send()

    @api.model
    def _cron_send_cashflow_reports(self):
        """Scheduled cron: send to all active alert configs."""
        configs = self.search([('active', '=', True)])
        for config in configs:
            try:
                config._send_report()
            except Exception:
                pass
