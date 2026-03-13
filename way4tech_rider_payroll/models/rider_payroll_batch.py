# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.fields import Command
from odoo.exceptions import UserError, ValidationError


class RiderPayrollBatch(models.Model):
    _name = 'rider.payroll.batch'
    _description = 'Rider Payroll Batch'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, name desc'
    _check_company_auto = True

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        tracking=True,
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
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
        required=True,
        tracking=True,
        help='The client this payroll batch is billed to (e.g., HungerStation)',
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Analytic Account',
        check_company=True,
        tracking=True,
        help='Analytic account for cost tracking per client',
    )
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Payroll Journal',
        required=True,
        check_company=True,
        domain=[('type', 'in', ['general', 'purchase'])],
        tracking=True,
    )
    salary_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Salary Expense Account',
        check_company=True,
        tracking=True,
        help='Expense account for company rider salaries (Dr)',
    )
    salary_payable_account_id = fields.Many2one(
        comodel_name='account.account',
        string='Salary Payable Account',
        check_company=True,
        tracking=True,
        help='Liability account for salaries payable (Cr)',
    )
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('imported', 'Imported'),
            ('validated', 'Validated'),
            ('posted', 'Posted'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        required=True,
        copy=False,
        tracking=True,
    )
    line_ids = fields.One2many(
        comodel_name='rider.payroll.line',
        inverse_name='batch_id',
        string='Rider Lines',
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
        string='Currency',
        readonly=True,
    )
    notes = fields.Text(string='Notes')

    # Computed totals
    rider_count = fields.Integer(string='Riders', compute='_compute_totals')
    employee_count = fields.Integer(string='Company Riders', compute='_compute_totals')
    freelancer_count = fields.Integer(string='Freelancers', compute='_compute_totals')
    total_fixed_salary = fields.Monetary(string='Total Fixed Salary', compute='_compute_totals', store=True)
    total_order_earnings = fields.Monetary(string='Total Order Earnings', compute='_compute_totals', store=True)
    total_bonus = fields.Monetary(string='Total Bonus', compute='_compute_totals', store=True)
    total_petrol = fields.Monetary(string='Total Petrol', compute='_compute_totals', store=True)
    total_deductions = fields.Monetary(string='Total Deductions', compute='_compute_totals', store=True)
    total_net_payable = fields.Monetary(string='Total Net Payable', compute='_compute_totals', store=True)

    # Links to generated accounting documents
    move_ids = fields.One2many(
        comodel_name='account.move',
        inverse_name='rider_payroll_batch_id',
        string='Journal Entries',
    )
    move_count = fields.Integer(string='Journal Entries', compute='_compute_move_count')
    bill_count = fields.Integer(string='Vendor Bills', compute='_compute_move_count')

    @api.depends('line_ids', 'line_ids.net_payable', 'line_ids.rider_type',
                 'line_ids.fixed_salary', 'line_ids.order_earnings', 'line_ids.bonus',
                 'line_ids.petrol', 'line_ids.deduction', 'line_ids.advance_deduction', 'line_ids.fine')
    def _compute_totals(self):
        for batch in self:
            lines = batch.line_ids
            batch.rider_count = len(lines)
            batch.employee_count = len(lines.filtered(lambda l: l.rider_type == 'employee'))
            batch.freelancer_count = len(lines.filtered(lambda l: l.rider_type == 'freelancer'))
            batch.total_fixed_salary = sum(lines.mapped('fixed_salary'))
            batch.total_order_earnings = sum(lines.mapped('order_earnings'))
            batch.total_bonus = sum(lines.mapped('bonus'))
            batch.total_petrol = sum(lines.mapped('petrol'))
            batch.total_deductions = sum(lines.mapped('deduction')) + sum(lines.mapped('advance_deduction')) + sum(lines.mapped('fine'))
            batch.total_net_payable = sum(lines.mapped('net_payable'))

    def _compute_move_count(self):
        for batch in self:
            all_moves = batch.move_ids
            batch.move_count = len(all_moves.filtered(lambda m: m.move_type == 'entry'))
            batch.bill_count = len(all_moves.filtered(lambda m: m.move_type == 'in_invoice'))

    @api.constrains('period_start', 'period_end')
    def _check_period_dates(self):
        for batch in self:
            if batch.period_start and batch.period_end and batch.period_start > batch.period_end:
                raise ValidationError(_('Period Start must be before Period End.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('rider.payroll.batch') or _('New')
        return super().create(vals_list)

    def action_validate(self):
        for batch in self:
            if batch.state not in ('draft', 'imported'):
                raise UserError(_('Only Draft or Imported batches can be validated.'))
            if not batch.line_ids:
                raise UserError(_('Cannot validate a batch with no rider lines.'))
            if not batch.salary_account_id:
                raise UserError(_('Please set the Salary Expense Account before validating.'))
            if not batch.salary_payable_account_id:
                raise UserError(_('Please set the Salary Payable Account before validating.'))
            batch.line_ids.write({'state': 'validated'})
            batch.write({'state': 'validated'})
        return True

    def action_post(self):
        """Post the payroll batch: create journal entries for employees and vendor bills for freelancers."""
        for batch in self:
            if batch.state != 'validated':
                raise UserError(_('Only Validated batches can be posted.'))
            batch._create_accounting_entries()
            batch.write({'state': 'posted'})
        return True

    def _create_accounting_entries(self):
        self.ensure_one()
        move_vals_list = []
        bill_vals_list = []
        employee_lines = self.line_ids.filtered(lambda l: l.rider_type == 'employee' and l.net_payable > 0)
        freelancer_lines = self.line_ids.filtered(lambda l: l.rider_type == 'freelancer' and l.net_payable > 0)

        analytic_distribution = {}
        if self.analytic_account_id:
            analytic_distribution = {str(self.analytic_account_id.id): 100.0}

        # Create one consolidated journal entry for all company riders
        if employee_lines:
            move_line_vals = []
            total_debit = 0.0
            for line in employee_lines:
                net = line.net_payable
                total_debit += net
                line_analytic = {}
                if line.analytic_account_id:
                    line_analytic = {str(line.analytic_account_id.id): 100.0}
                elif analytic_distribution:
                    line_analytic = analytic_distribution
                move_line_vals.append(Command.create({
                    'name': _('Salary: %s') % line.name,
                    'account_id': self.salary_account_id.id,
                    'debit': net,
                    'credit': 0.0,
                    'partner_id': line.employee_id.work_contact_id.id if line.employee_id and line.employee_id.work_contact_id else False,
                    'analytic_distribution': line_analytic or False,
                }))
            # Counterpart: credit salary payable
            move_line_vals.append(Command.create({
                'name': _('Salaries Payable – %s') % self.name,
                'account_id': self.salary_payable_account_id.id,
                'debit': 0.0,
                'credit': total_debit,
                'analytic_distribution': analytic_distribution or False,
            }))
            move_vals_list.append({
                'move_type': 'entry',
                'journal_id': self.journal_id.id,
                'date': self.date,
                'ref': _('Payroll – %s') % self.name,
                'company_id': self.company_id.id,
                'rider_payroll_batch_id': self.id,
                'line_ids': move_line_vals,
            })

        # Create vendor bills for each freelancer
        purchase_journal = self.env['account.journal'].search([
            *self.env['account.journal']._check_company_domain(self.company_id),
            ('type', '=', 'purchase'),
        ], limit=1)
        if not purchase_journal:
            raise UserError(_('No purchase journal found. Please configure a purchase journal.'))

        for line in freelancer_lines:
            if not line.vendor_id:
                raise UserError(_('Freelancer "%s" has no vendor partner set. Please link a vendor.') % line.name)
            net = line.net_payable
            line_analytic = {}
            if line.analytic_account_id:
                line_analytic = {str(line.analytic_account_id.id): 100.0}
            elif analytic_distribution:
                line_analytic = analytic_distribution
            bill_vals_list.append({
                'move_type': 'in_invoice',
                'journal_id': purchase_journal.id,
                'date': self.date,
                'invoice_date': self.date,
                'partner_id': line.vendor_id.id,
                'ref': _('Payroll %s – %s') % (self.name, line.name),
                'company_id': self.company_id.id,
                'rider_payroll_batch_id': self.id,
                'invoice_line_ids': [Command.create({
                    'name': _('Rider Payroll: %s | %s – %s') % (
                        line.name, self.period_start, self.period_end),
                    'quantity': 1.0,
                    'price_unit': net,
                    'analytic_distribution': line_analytic or False,
                })],
            })

        AccountMove = self.env['account.move'].sudo()
        created_moves = AccountMove.browse()
        if move_vals_list:
            moves = AccountMove.create(move_vals_list)
            moves._post(soft=False)
            created_moves |= moves
            employee_lines.write({'state': 'posted'})

        if bill_vals_list:
            bills = AccountMove.create(bill_vals_list)
            created_moves |= bills
            # Bills remain in draft for review; accountant will post them
            freelancer_lines.write({'state': 'posted'})

        return created_moves

    def action_cancel(self):
        for batch in self:
            if batch.state == 'posted':
                raise UserError(_('Posted batches cannot be cancelled. Please reverse the accounting entries first.'))
            batch.line_ids.write({'state': 'draft'})
            batch.write({'state': 'cancelled'})
        return True

    def action_reset_to_draft(self):
        for batch in self:
            if batch.state == 'cancelled':
                batch.line_ids.write({'state': 'draft'})
                batch.write({'state': 'draft'})
        return True

    def action_view_journal_entries(self):
        self.ensure_one()
        entries = self.move_ids.filtered(lambda m: m.move_type == 'entry')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entries'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', entries.ids)],
        }

    def action_view_vendor_bills(self):
        self.ensure_one()
        bills = self.move_ids.filtered(lambda m: m.move_type == 'in_invoice')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bills'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('id', 'in', bills.ids)],
        }
