from odoo import api, fields, models, _
from odoo.exceptions import UserError


class EmployeeDeduction(models.Model):
    """
    Tracks advances and charges given to employees/freelancers.
    Each posted record creates a proper account.move (journal entry)
    so the balance flows through Odoo's standard double-entry ledger.

    Debit entry (charge given):
        Dr  Employee Advances / Deduction Account
        Cr  Company Payable / Cash / Clearing Account

    When the salary deduction is processed via payslip, the salary rules
    (ADV_DED_RULE, FUEL_DED_RULE, etc.) should have account_debit set to
    the same Employee Advances account so that it clears on payslip confirmation.
    """
    _name = 'way4tech.employee.deduction'
    _description = 'Employee Advance / Deduction'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, name desc'

    name = fields.Char(
        string='Reference',
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Employee',
        tracking=True,
    )
    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Partner',
        compute='_compute_partner_id',
        store=True,
        readonly=False,
        help='Used for the journal entry. Auto-filled from employee address.',
    )
    deduction_type = fields.Selection(
        selection=[
            ('advance', 'Advance'),
            ('fuel', 'Fuel'),
            ('sim', 'SIM Charges'),
            ('loan', 'Loan'),
            ('traffic', 'Traffic Violation'),
            ('rent', 'Rent'),
            ('other', 'Other'),
        ],
        string='Type',
        required=True,
        default='advance',
        tracking=True,
    )
    description = fields.Char(
        string='Description',
        required=True,
        tracking=True,
    )
    amount = fields.Monetary(
        string='Amount',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        store=True,
        readonly=True,
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Journal',
        required=True,
        default=lambda self: self._default_journal(),
        domain=[('type', 'in', ('general', 'cash', 'bank'))],
        help='Journal used to post the deduction entry.',
    )
    debit_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Debit Account',
        required=True,
        help='Account debited when the advance/charge is given '
             '(e.g. Employee Advances, Loans to Staff). '
             'This account is credited back when the payslip deduction is processed.',
    )
    credit_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Credit Account',
        required=True,
        help='Account credited when the advance/charge is given '
             '(e.g. Cash, Bank, or a clearing payable account).',
    )
    move_id = fields.Many2one(
        comodel_name='account.move',
        string='Journal Entry',
        readonly=True,
        copy=False,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('posted', 'Posted'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        tracking=True,
        copy=False,
    )
    recovered_amount = fields.Monetary(
        string='Recovered Amount',
        currency_field='currency_id',
        default=0.0,
        tracking=True,
        help='Total amount recovered so far via salary deductions. Updated each time a salary import processes this record.',
    )
    outstanding = fields.Monetary(
        string='Outstanding Balance',
        compute='_compute_outstanding',
        store=True,
        currency_field='currency_id',
        help='Remaining balance still to be recovered: Amount − Recovered Amount.',
    )
    salary_import_line_id = fields.Many2one(
        comodel_name='way4tech.salary.import.line',
        string='Last Recovered In',
        readonly=True,
        copy=False,
        help='The most recent salary import line that recovered part or all of this deduction.',
    )
    note = fields.Text(string='Note')

    @api.depends('amount', 'recovered_amount')
    def _compute_outstanding(self):
        for rec in self:
            rec.outstanding = rec.amount - rec.recovered_amount

    @api.model
    def _default_journal(self):
        # Try to find a journal named "Employee Deductions" or fall back to first general journal
        journal = self.env['account.journal'].search(
            [('name', 'ilike', 'employee'), ('type', '=', 'general'), ('company_id', '=', self.env.company.id)],
            limit=1,
        )
        if not journal:
            journal = self.env['account.journal'].search(
                [('type', '=', 'general'), ('company_id', '=', self.env.company.id)],
                limit=1,
            )
        return journal

    @api.depends('employee_id')
    def _compute_partner_id(self):
        for rec in self:
            if rec.employee_id and rec.employee_id.address_home_id:
                rec.partner_id = rec.employee_id.address_home_id
            elif rec.employee_id and rec.employee_id.user_id and rec.employee_id.user_id.partner_id:
                rec.partner_id = rec.employee_id.user_id.partner_id
            elif not rec.partner_id:
                rec.partner_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'way4tech.employee.deduction'
                ) or _('New')
        return super().create(vals_list)

    def action_post(self):
        """Create the accounting journal entry and mark as posted."""
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('Only draft records can be posted.'))
            if not rec.partner_id:
                raise UserError(
                    _('No partner set for %s. Please link the employee to a partner '
                      '(set Private Information → Private Address on the employee).') % rec.employee_id.name
                )

            move_vals = {
                'move_type': 'entry',
                'journal_id': rec.journal_id.id,
                'date': rec.date,
                'ref': '%s — %s' % (rec.name, rec.description),
                'company_id': rec.company_id.id,
                'line_ids': [
                    (0, 0, {
                        'name': rec.description,
                        'partner_id': rec.partner_id.id,
                        'account_id': rec.debit_account_id.id,
                        'debit': rec.amount,
                        'credit': 0.0,
                    }),
                    (0, 0, {
                        'name': rec.description,
                        'partner_id': rec.partner_id.id,
                        'account_id': rec.credit_account_id.id,
                        'debit': 0.0,
                        'credit': rec.amount,
                    }),
                ],
            }
            _category = self.env.ref('way4tech_logistics.category_advance', raise_if_not_found=False)
            if _category:
                move_vals['way4tech_category_id'] = _category.id
            move = self.env['account.move'].create(move_vals)
            move.action_post()
            rec.write({'move_id': move.id, 'state': 'posted'})

    def action_cancel(self):
        """Create a reversal journal entry and mark as cancelled.
        Uses _reverse_moves() so the original entry remains visible in the audit trail
        and the reversal neutralises the accounting effect — standard Odoo practice."""
        for rec in self:
            if rec.state != 'posted':
                raise UserError(_('Only posted records can be cancelled.'))
            if rec.move_id and rec.move_id.state == 'posted':
                reversal = rec.move_id._reverse_moves(
                    default_values_list=[{
                        'ref': _('Reversal of %s') % rec.move_id.name,
                        'date': fields.Date.today(),
                    }],
                )
                reversal.action_post()
            rec.state = 'cancelled'

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state == 'cancelled':
                rec.state = 'draft'

    def action_view_journal_entry(self):
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


class EmployeeDeductionSummary(models.Model):
    """
    Read-only summary of outstanding deduction balances per employee,
    derived from account.move.line entries.

    For a full partner ledger, use Odoo's standard Accounting > Reporting >
    Partner Ledger and filter by the relevant accounts.
    """
    _name = 'way4tech.employee.deduction.summary'
    _description = 'Employee Deduction Balance Summary'
    _auto = False  # SQL view
    _order = 'employee_name'

    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    employee_name = fields.Char(string='Employee Name', readonly=True)
    deduction_type = fields.Selection(
        selection=[
            ('advance', 'Advance'),
            ('fuel', 'Fuel'),
            ('sim', 'SIM Charges'),
            ('loan', 'Loan'),
            ('traffic', 'Traffic Violation'),
            ('rent', 'Rent'),
            ('other', 'Other'),
        ],
        string='Type',
        readonly=True,
    )
    total_amount = fields.Float(string='Total Charged', readonly=True)
    recovered_amount = fields.Float(string='Recovered in Salary', readonly=True)
    outstanding = fields.Float(string='Outstanding Balance', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)

    def init(self):
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW way4tech_employee_deduction_summary AS
            SELECT
                ROW_NUMBER() OVER () AS id,
                ed.employee_id,
                emp.name AS employee_name,
                ed.deduction_type,
                SUM(ed.amount) AS total_amount,
                SUM(ed.recovered_amount) AS recovered_amount,
                SUM(ed.amount - ed.recovered_amount) AS outstanding,
                ed.company_id
            FROM way4tech_employee_deduction ed
            LEFT JOIN hr_employee emp ON emp.id = ed.employee_id
            WHERE ed.state = 'posted'
            GROUP BY ed.employee_id, emp.name, ed.deduction_type, ed.company_id
        """)
