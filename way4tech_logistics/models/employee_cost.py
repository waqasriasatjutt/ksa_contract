from odoo import api, fields, models, _
from odoo.exceptions import UserError


class Way4TechEmployeeCost(models.Model):
    _name = 'way4tech.employee.cost'
    _description = 'Employee Additional KSA Cost'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'period_start desc, name desc'

    name = fields.Char(
        string='Reference',
        readonly=True,
        copy=False,
        default=lambda self: _('New'),
    )
    employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Employee',
        required=True,
        tracking=True,
    )
    period_start = fields.Date(string='Period Start', required=True)
    period_end = fields.Date(string='Period End', required=True)
    client_id = fields.Many2one(
        comodel_name='res.partner',
        string='Assigned Client',
        tracking=True,
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
        store=True,
    )
    basic_salary = fields.Monetary(
        string='Basic Salary',
        currency_field='currency_id',
    )
    gosi_rate = fields.Float(
        string='GOSI Rate %',
        default=11.75,
        digits=(5, 2),
        help='Total GOSI contribution rate (employer share). KSA standard is 11.75%.',
    )
    gosi_amount = fields.Monetary(
        string='GOSI Contribution',
        currency_field='currency_id',
    )
    iqama_amount = fields.Monetary(
        string='Iqama/Residency Cost',
        currency_field='currency_id',
    )
    insurance_amount = fields.Monetary(
        string='Medical Insurance',
        currency_field='currency_id',
    )
    saudization_amount = fields.Monetary(
        string='Saudization (Nitaqat) Cost',
        currency_field='currency_id',
    )
    other_costs = fields.Monetary(
        string='Other Costs',
        currency_field='currency_id',
    )
    total_cost = fields.Monetary(
        string='Total Monthly Cost',
        compute='_compute_total',
        store=True,
        currency_field='currency_id',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('confirmed', 'Confirmed'),
        ],
        string='Status',
        default='draft',
        tracking=True,
        copy=False,
    )
    notes = fields.Text(string='Notes')
    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Journal Entry',
        readonly=True,
        copy=False,
    )

    @api.depends(
        'basic_salary', 'gosi_amount', 'iqama_amount',
        'insurance_amount', 'saudization_amount', 'other_costs',
    )
    def _compute_total(self):
        for rec in self:
            rec.total_cost = (
                rec.basic_salary
                + rec.gosi_amount
                + rec.iqama_amount
                + rec.insurance_amount
                + rec.saudization_amount
                + rec.other_costs
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'way4tech.employee.cost'
                ) or _('New')
        return super().create(vals_list)

    def action_compute_gosi(self):
        """Auto-calculate GOSI from basic_salary * gosi_rate / 100."""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Cannot recalculate GOSI on a confirmed record. Reset to Draft first.'))
        self.gosi_amount = self.basic_salary * self.gosi_rate / 100.0

    def action_confirm(self):
        self.ensure_one()
        self.state = 'confirmed'

    def action_reset_draft(self):
        self.ensure_one()
        self.state = 'draft'

    def action_post_expenses(self):
        """Create a journal entry for all non-zero compliance costs (GOSI, Iqama, Insurance, Saudization)."""
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(_('Please confirm the record before posting expenses.'))
        if self.move_id:
            raise UserError(_('A journal entry already exists for this record.'))

        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)

        if not settings.employee_cost_journal_id:
            raise UserError(_('Please set the Employee Compliance Journal in Payroll & Accounting Setup.'))
        if not settings.compliance_payable_account_id:
            raise UserError(_('Please set the Compliance Costs Payable Account in Payroll & Accounting Setup.'))

        analytic = self.analytic_account_id or settings.default_analytic_account_id
        analytic_distribution = {str(analytic.id): 100} if analytic else False

        cost_map = [
            ('gosi_amount', 'gosi_expense_account_id', 'GOSI Employer Contribution'),
            ('iqama_amount', 'iqama_expense_account_id', 'Iqama/Residency Cost'),
            ('insurance_amount', 'insurance_expense_account_id', 'Medical Insurance'),
            ('saudization_amount', 'saudization_expense_account_id', 'Saudization (Nitaqat)'),
            ('other_costs', 'other_compliance_account_id', 'Other Compliance Cost'),
        ]

        line_ids = []
        total_posted = 0.0
        for amount_field, acc_field, label in cost_map:
            amount = getattr(self, amount_field)
            account = getattr(settings, acc_field)
            if amount and account:
                line_data = {
                    'name': '%s - %s' % (label, self.employee_id.name),
                    'account_id': account.id,
                    'debit': amount,
                    'credit': 0.0,
                }
                if analytic_distribution:
                    line_data['analytic_distribution'] = analytic_distribution
                line_ids.append((0, 0, line_data))
                total_posted += amount

        if not line_ids:
            raise UserError(_(
                'No compliance costs to post. Please enter cost amounts and set the '
                'expense accounts in Payroll & Accounting Setup.'
            ))

        # Single credit line to compliance payable
        credit_line = {
            'name': 'Compliance Costs Payable - %s' % self.employee_id.name,
            'account_id': settings.compliance_payable_account_id.id,
            'debit': 0.0,
            'credit': total_posted,
        }
        if analytic_distribution:
            credit_line['analytic_distribution'] = analytic_distribution
        line_ids.append((0, 0, credit_line))

        move = self.env['account.move'].create({
            'move_type': 'entry',
            'journal_id': settings.employee_cost_journal_id.id,
            'date': self.period_end,
            'ref': self.name,
            'company_id': self.company_id.id,
            'line_ids': line_ids,
        })
        move.action_post()
        self.write({'move_id': move.id})
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entry'),
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_move(self):
        self.ensure_one()
        if not self.move_id:
            raise UserError(_('No journal entry linked to this record.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entry'),
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
