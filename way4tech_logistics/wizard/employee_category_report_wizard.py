import base64
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class Way4TechEmployeeCategoryReportWizard(models.TransientModel):
    """
    Generates a category-wise deduction/expense report for a single employee.
    Shows totals per deduction type (Advance, Loan, Salary, Iqama, etc.)
    for a selected month/period.
    Can be printed as PDF or emailed directly to the employee.
    """
    _name = 'way4tech.employee.category.report.wizard'
    _description = 'Employee Category-wise Report Wizard'

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    date_from = fields.Date(
        string='From',
        required=True,
        default=lambda self: fields.Date.today().replace(day=1),
    )
    date_to = fields.Date(
        string='To',
        required=True,
        default=fields.Date.today,
    )
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company,
    )
    include_salary = fields.Boolean(string='Include Salary Import Lines', default=True)

    # ── Data Methods ──────────────────────────────────────────────────────────

    def _get_deduction_data(self):
        """Aggregate posted deductions by type for the selected employee + period."""
        domain = [
            ('employee_id', '=', self.employee_id.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('state', '=', 'posted'),
        ]
        if self.company_id:
            domain += [('company_id', '=', self.company_id.id)]
        deductions = self.env['way4tech.employee.deduction'].search(domain)
        selection = dict(
            self.env['way4tech.employee.deduction']._fields['deduction_type'].selection
        )
        totals = {}
        for ded in deductions:
            label = selection.get(ded.deduction_type, ded.deduction_type)
            totals.setdefault(label, {'total': 0.0, 'count': 0})
            totals[label]['total'] += ded.amount
            totals[label]['count'] += 1
        return [
            {'category': k, 'total': v['total'], 'count': v['count']}
            for k, v in sorted(totals.items())
        ]

    def _get_salary_data(self):
        """Get net payable from salary import lines for the period."""
        if not self.include_salary:
            return []
        domain = [
            ('employee_id', '=', self.employee_id.id),
            ('import_id.period_start', '>=', self.date_from),
            ('import_id.period_end', '<=', self.date_to),
            ('import_id.state', 'in', ('imported', 'done')),
        ]
        if self.company_id:
            domain += [('import_id.company_id', '=', self.company_id.id)]
        lines = self.env['way4tech.salary.import.line'].search(domain)
        if not lines:
            return []
        return [{
            'category': _('Salary — Net Payable'),
            'total': sum(lines.mapped('net_payable')),
            'count': len(lines),
        }]

    def get_report_data(self):
        rows = self._get_deduction_data() + self._get_salary_data()
        grand_total = sum(r['total'] for r in rows)
        return rows, grand_total

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_print_report(self):
        return self.env.ref(
            'way4tech_logistics.action_report_employee_category'
        ).report_action(self)

    def action_send_email(self):
        """Generate PDF and send to employee's work email."""
        emp = self.employee_id
        if not emp.work_email:
            raise UserError(_(
                'Employee %s has no Work Email configured.\n'
                'Please set the Work Email in the employee form first.'
            ) % emp.name)

        # Render PDF
        pdf_bytes, _mime = self.env['ir.actions.report'].sudo()._render_qweb_pdf(
            'way4tech_logistics.action_report_employee_category',
            self.ids,
        )
        attachment = self.env['ir.attachment'].sudo().create({
            'name': f'Category_Report_{emp.name}_{self.date_from}_{self.date_to}.pdf',
            'datas': base64.b64encode(pdf_bytes),
            'mimetype': 'application/pdf',
            'res_model': self._name,
            'res_id': self.id,
        })
        self.env['mail.mail'].sudo().create({
            'subject': (
                f'[Way4Tech] Category Report — {emp.name} '
                f'({self.date_from} to {self.date_to})'
            ),
            'body_html': (
                f'<p>Dear {emp.name},</p>'
                f'<p>Please find your category-wise expense / deduction report attached '
                f'for the period <strong>{self.date_from}</strong> to '
                f'<strong>{self.date_to}</strong>.</p>'
                f'<p>Regards,<br/>{self.env.company.name}</p>'
            ),
            'email_to': emp.work_email,
            'email_from': self.env.company.email or 'noreply@way4tech.com',
            'attachment_ids': [(4, attachment.id)],
        }).send()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'message': _('Report sent to %s') % emp.work_email,
                'type': 'success',
            },
        }

    def action_generate_whatsapp_link(self):
        """Generate a WhatsApp deep-link with a summary message."""
        emp = self.employee_id
        phone = emp.mobile_phone or emp.work_phone or ''
        # Strip non-digit characters
        phone_clean = ''.join(filter(str.isdigit, phone))
        rows, grand_total = self.get_report_data()
        lines = '\n'.join(
            f'• {r["category"]}: SAR {r["total"]:,.2f}' for r in rows
        )
        message = (
            f'Dear {emp.name},\n\n'
            f'Your Way4Tech expense summary for {self.date_from} to {self.date_to}:\n\n'
            f'{lines}\n\n'
            f'Total: SAR {grand_total:,.2f}\n\n'
            f'Regards,\n{self.env.company.name}'
        )
        import urllib.parse
        wa_url = f'https://wa.me/{phone_clean}?text={urllib.parse.quote(message)}'
        return {
            'type': 'ir.actions.act_url',
            'url': wa_url,
            'target': 'new',
        }
