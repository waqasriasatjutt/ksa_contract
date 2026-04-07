from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SalaryImport(models.Model):
    _name = 'way4tech.salary.import'
    _description = 'Worker Salary Import'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, name desc'

    name = fields.Char(
        string='Reference',
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True,
    )
    date = fields.Date(
        string='Import Date',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    period_start = fields.Date(
        string='Period Start',
        required=True,
        tracking=True,
    )
    period_end = fields.Date(
        string='Period End',
        required=True,
        tracking=True,
    )
    client_id = fields.Many2one(
        comodel_name='res.partner',
        string='Client',
        tracking=True,
    )
    platform_id = fields.Many2one(
        comodel_name='way4tech.platform.config',
        string='Default Platform',
        tracking=True,
        help='Default platform salary rules applied to all lines. '
             'Individual lines can override.',
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        tracking=True,
    )
    currency_id = fields.Many2one(
        comodel_name='res.currency',
        related='company_id.currency_id',
        string='Currency',
        readonly=True,
        store=True,
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('imported', 'Imported'),
            ('done', 'Done'),
        ],
        string='Status',
        default='draft',
        tracking=True,
        copy=False,
    )
    line_ids = fields.One2many(
        comodel_name='way4tech.salary.import.line',
        inverse_name='import_id',
        string='Salary Lines',
    )
    accounting_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Journal Entry',
        readonly=True,
        copy=False,
    )

    # ── Computed posting config (read from settings — for display/verification) ─
    posting_expense_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Salary Expense Account',
        compute='_compute_posting_config',
        help='Account that will be debited for each employee salary (from Payroll & Accounting Setup).',
    )
    posting_payable_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Salary Payable Account',
        compute='_compute_posting_config',
        help='Account that will be credited for each employee salary (from Payroll & Accounting Setup).',
    )
    posting_journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Payroll Journal',
        compute='_compute_posting_config',
        help='Journal used when posting salary entries (from Payroll & Accounting Setup).',
    )
    posting_ready = fields.Boolean(
        compute='_compute_posting_config',
        help='True when all required posting accounts and journal are configured.',
    )

    @api.depends('company_id')
    def _compute_posting_config(self):
        for rec in self:
            settings = self.env['way4tech.payroll.settings'].get_for_company(
                rec.company_id.id
            )
            rec.posting_expense_account_id = settings.salary_expense_account_id
            rec.posting_payable_account_id = settings.salary_payable_account_id
            rec.posting_journal_id = settings.payroll_journal_id
            rec.posting_ready = bool(
                settings.salary_expense_account_id
                and settings.salary_payable_account_id
                and settings.payroll_journal_id
            )

    total_employees = fields.Integer(
        string='Total Employees',
        compute='_compute_totals',
        store=True,
    )
    total_net = fields.Monetary(
        string='Total Net Payable',
        compute='_compute_totals',
        store=True,
        currency_field='currency_id',
    )
    error_count = fields.Integer(
        string='Errors',
        compute='_compute_totals',
        store=True,
    )
    notes = fields.Text(string='Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'way4tech.salary.import'
                ) or _('New')
        return super().create(vals_list)

    @api.onchange('client_id')
    def _onchange_client_id(self):
        """Auto-fill analytic account from the food delivery partner.
        This enables per-partner profit tracking via analytic reports."""
        if self.client_id and not self.analytic_account_id:
            analytic = self.env['account.analytic.account'].search([
                ('partner_id', '=', self.client_id.id),
            ], limit=1)
            if analytic:
                self.analytic_account_id = analytic

    @api.depends('line_ids', 'line_ids.net_payable', 'line_ids.has_error', 'line_ids.employee_id')
    def _compute_totals(self):
        for rec in self:
            rec.total_employees = len(rec.line_ids.filtered(lambda l: l.employee_id))
            rec.total_net = sum(rec.line_ids.mapped('net_payable'))
            rec.error_count = len(rec.line_ids.filtered(lambda l: l.has_error))

    def action_mark_imported(self):
        """Allow manually-entered lines to proceed to payslip creation without using Excel import."""
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Please add salary lines before marking as ready.'))
        self.state = 'imported'

    def action_view_ledger_entries(self):
        """Open account.move journal entries linked to this import via deduction records."""
        self.ensure_one()
        deductions = self.env['way4tech.employee.deduction'].search([
            ('salary_import_line_id.import_id', '=', self.id),
        ])
        move_ids = deductions.mapped('move_id').ids
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entries'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', move_ids)],
        }

    def action_fill_from_ledger(self):
        """Auto-fill office deduction fields from each employee's outstanding posted deductions."""
        self.ensure_one()
        if self.state not in ('draft', 'imported'):
            raise UserError(_('You can only fill from ledger on draft or imported records.'))

        Deduction = self.env['way4tech.employee.deduction']
        field_map = {
            'advance': 'advance_deduction',
            'fuel': 'fuel_deduction',
            'sim': 'sim_charges',
            'loan': 'loan',
            'traffic': 'traffic_violation',
            'rent': 'rent',
        }
        for line in self.line_ids:
            if not line.employee_id:
                continue  # can only fill for matched employees

            # Find posted deductions with remaining outstanding balance
            deductions = Deduction.search([
                ('state', '=', 'posted'),
                ('outstanding', '>', 0),
                ('employee_id', '=', line.employee_id.id),
                ('company_id', '=', self.company_id.id),
            ])
            # Accumulate outstanding balance per type
            totals = {}
            for ded in deductions:
                totals[ded.deduction_type] = totals.get(ded.deduction_type, 0.0) + ded.outstanding

            for ded_type, fname in field_map.items():
                # Only fill if the field is currently zero — never overwrite
                # an amount already entered (e.g. from the imported Excel)
                if totals.get(ded_type) and not getattr(line, fname, 0.0):
                    line[fname] = totals[ded_type]

            # Fill loan_balance_before with total outstanding loan balance
            if not line.loan_balance_before and totals.get('loan', 0.0) > 0:
                line.loan_balance_before = totals.get('loan', 0.0)

    def action_post_to_accounting(self):
        """
        Simple direct posting: create one journal entry for all employee
        salary lines in this import. No payslips, no salary rules, no tax.

        Journal entry:
          Dr  Salary Expense Account   (per employee, net_payable)
          Cr  Salary Payable Account   (per employee, net_payable)
        """
        self.ensure_one()
        if self.state not in ('draft', 'imported'):
            raise UserError(_('This salary sheet has already been posted.'))

        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)
        if not settings.salary_expense_account_id:
            raise UserError(_('Set the Salary Expense Account in Settings → Payroll & Accounting Setup.'))
        if not settings.salary_payable_account_id:
            raise UserError(_('Set the Salary Payable Account in Settings → Payroll & Accounting Setup.'))
        if not settings.payroll_journal_id:
            raise UserError(_('Set the Payroll Journal in Settings → Payroll & Accounting Setup.'))

        valid_lines = self.line_ids.filtered(
            lambda l: not l.has_error and l.employee_id and l.net_payable > 0
        )
        if not valid_lines:
            raise UserError(_('No valid employee lines with a net salary amount to post.'))

        currency = self.company_id.currency_id
        debit_acc_id = settings.salary_expense_account_id.id
        credit_acc_id = settings.salary_payable_account_id.id

        # Build analytic distribution if an analytic account is set
        analytic = (
            self.analytic_account_id
            or settings.default_analytic_account_id
        )
        analytic_distribution = {str(analytic.id): 100} if analytic else {}

        # Rebuild lines with analytic if available
        move_lines = []
        for line in valid_lines:
            partner_id = line.employee_id.user_partner_id.id or False
            amount = currency.round(line.net_payable)
            debit_vals = {
                'name': line.employee_id.name,
                'account_id': debit_acc_id,
                'debit': amount,
                'credit': 0.0,
                'tax_ids': [],
                'partner_id': partner_id,
            }
            credit_vals = {
                'name': line.employee_id.name,
                'account_id': credit_acc_id,
                'debit': 0.0,
                'credit': amount,
                'tax_ids': [],
                'partner_id': partner_id,
            }
            if analytic_distribution:
                debit_vals['analytic_distribution'] = analytic_distribution
            move_lines += [(0, 0, debit_vals), (0, 0, credit_vals)]

        move = self.env['account.move'].create({
            'narration': _('Salary — %s  |  %s to %s') % (
                self.name, self.period_start, self.period_end),
            'ref': self.name,
            'journal_id': settings.payroll_journal_id.id,
            'date': self.period_end,
            'line_ids': move_lines,
        })
        move.action_post()

        self._mark_deductions_recovered_internal()

        self.write({
            'state': 'done',
            'accounting_move_id': move.id,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _('Salary Journal Entry'),
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_reset_to_draft(self):
        """Reset a posted salary import back to Imported state for correction.
        Cancels and deletes the linked journal entry so it can be re-posted."""
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_('Only Done records can be reset to draft.'))
        if self.accounting_move_id:
            move = self.accounting_move_id
            if move.state == 'posted':
                move.button_cancel()
            move.unlink()
        self.write({
            'state': 'imported',
            'accounting_move_id': False,
        })

    def action_view_accounting_entry(self):
        self.ensure_one()
        if not self.accounting_move_id:
            raise UserError(_('No journal entry linked to this import.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Salary Journal Entry'),
            'res_model': 'account.move',
            'res_id': self.accounting_move_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _mark_deductions_recovered_internal(self):
        """Internal version of mark_deductions_recovered, usable from action_process_and_post."""
        Deduction = self.env['way4tech.employee.deduction']
        field_map = {
            'advance': 'advance_deduction',
            'fuel': 'fuel_deduction',
            'sim': 'sim_charges',
            'loan': 'loan',
            'traffic': 'traffic_violation',
            'rent': 'rent',
        }
        for line in self.line_ids.filtered(lambda l: not l.has_error and l.employee_id):
            for ded_type, fname in field_map.items():
                amount_to_recover = getattr(line, fname, 0.0)
                if not amount_to_recover:
                    continue
                deductions = Deduction.search([
                    ('state', '=', 'posted'),
                    ('outstanding', '>', 0),
                    ('employee_id', '=', line.employee_id.id),
                    ('deduction_type', '=', ded_type),
                    ('company_id', '=', self.company_id.id),
                ], order='date asc, id asc')
                remaining = amount_to_recover
                for ded in deductions:
                    if remaining <= 0:
                        break
                    current_outstanding = ded.amount - ded.recovered_amount
                    apply = min(current_outstanding, remaining)
                    ded.recovered_amount += apply
                    remaining -= apply
                    ded.salary_import_line_id = line.id

    def action_mark_deductions_recovered(self):
        """Mark employee deductions as recovered (link to salary import lines).
        Called after payslips are confirmed so the outstanding balance clears."""
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_('Payslips must be confirmed (Done) before marking deductions as recovered.'))

        Deduction = self.env['way4tech.employee.deduction']
        field_map = {
            'advance': 'advance_deduction',
            'fuel': 'fuel_deduction',
            'sim': 'sim_charges',
            'loan': 'loan',
            'traffic': 'traffic_violation',
            'rent': 'rent',
        }

        for line in self.line_ids.filtered(lambda l: not l.has_error and l.employee_id):
            for ded_type, fname in field_map.items():
                amount_to_recover = getattr(line, fname, 0.0)
                if not amount_to_recover:
                    continue
                # Find posted deductions with outstanding balance, oldest first (FIFO)
                deductions = Deduction.search([
                    ('state', '=', 'posted'),
                    ('outstanding', '>', 0),
                    ('employee_id', '=', line.employee_id.id),
                    ('deduction_type', '=', ded_type),
                    ('company_id', '=', self.company_id.id),
                ], order='date asc, id asc')

                remaining = amount_to_recover
                for ded in deductions:
                    if remaining <= 0:
                        break
                    current_outstanding = ded.amount - ded.recovered_amount
                    apply = min(current_outstanding, remaining)
                    ded.recovered_amount += apply
                    remaining -= apply
                    # Track which import line last made a recovery on this record
                    ded.salary_import_line_id = line.id

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Deductions Marked as Recovered'),
                'message': _('Employee advance/deduction records linked to this salary import.'),
                'type': 'success',
            },
        }

    def action_compute_all_salaries(self):
        """Recompute fixed_salary and order_adjustment from platform rules for every
        line that has a platform set.  Lines without a platform are left untouched."""
        self.ensure_one()
        computed = 0
        for line in self.line_ids:
            if line.platform_id and (line.valid_days or line.orders_completed):
                fixed, adj = line.platform_id.compute_salary(
                    line.valid_days, line.orders_completed
                )
                line.fixed_salary = fixed
                line.order_adjustment = adj
                computed += 1
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Salary Computed'),
                'message': _('%d lines recomputed from platform rules.') % computed,
                'type': 'success',
            },
        }

    def action_open_import_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Import from Excel'),
            'res_model': 'way4tech.salary.excel.import',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_import_id': self.id},
        }

