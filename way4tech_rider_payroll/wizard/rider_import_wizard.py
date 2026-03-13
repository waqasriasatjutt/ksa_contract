# -*- coding: utf-8 -*-
import base64
import io
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

# Expected Excel column headers (case-insensitive)
COLUMN_MAPPING = {
    'rider name': 'name',
    'name': 'name',
    'type': 'rider_type',
    'rider type': 'rider_type',
    'employee ref': 'employee_ref',
    'employee': 'employee_ref',
    'vendor ref': 'vendor_ref',
    'vendor': 'vendor_ref',
    'fixed salary': 'fixed_salary',
    'salary': 'fixed_salary',
    'order earnings': 'order_earnings',
    'orders': 'order_earnings',
    'order': 'order_earnings',
    'bonus': 'bonus',
    'petrol': 'petrol',
    'petrol allowance': 'petrol',
    'fuel': 'petrol',
    'deduction': 'deduction',
    'deductions': 'deduction',
    'advance': 'advance_deduction',
    'advance deduction': 'advance_deduction',
    'fine': 'fine',
    'fines': 'fine',
    'note': 'note',
    'notes': 'note',
    'analytic': 'analytic_ref',
    'analytic account': 'analytic_ref',
}

RIDER_TYPE_MAPPING = {
    'employee': 'employee',
    'company': 'employee',
    'staff': 'employee',
    'freelancer': 'freelancer',
    'vendor': 'freelancer',
    'outsource': 'freelancer',
    'contractor': 'freelancer',
    'subcontractor': 'freelancer',
}


class RiderImportWizard(models.TransientModel):
    _name = 'rider.import.wizard'
    _description = 'Rider Payroll Excel Import Wizard'

    file = fields.Binary(
        string='Excel File (.xlsx)',
        required=True,
        attachment=False,
    )
    file_name = fields.Char(string='File Name')
    batch_id = fields.Many2one(
        comodel_name='rider.payroll.batch',
        string='Add to Existing Batch',
        help='Leave empty to create a new payroll batch',
    )
    # Fields for new batch creation (used when batch_id is empty)
    client_id = fields.Many2one(
        comodel_name='res.partner',
        string='Client',
        help='Required when creating a new batch',
    )
    period_start = fields.Date(
        string='Period Start',
        default=lambda self: fields.Date.today().replace(day=1),
    )
    period_end = fields.Date(string='Period End', default=fields.Date.context_today)
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        string='Payroll Journal',
        domain=[('type', 'in', ['general', 'purchase'])],
    )
    analytic_account_id = fields.Many2one(
        comodel_name='account.analytic.account',
        string='Default Analytic Account',
    )
    default_rider_type = fields.Selection(
        selection=[
            ('employee', 'Company Rider (Employee)'),
            ('freelancer', 'Freelancer (Vendor)'),
        ],
        string='Default Rider Type',
        default='employee',
        help='Used when the Type column is missing or blank in the Excel file',
    )

    # Results
    error_log = fields.Text(string='Validation Errors', readonly=True)
    preview_line_ids = fields.One2many(
        comodel_name='rider.import.preview.line',
        inverse_name='wizard_id',
        string='Preview',
        readonly=True,
    )
    state = fields.Selection(
        selection=[('upload', 'Upload'), ('preview', 'Preview'), ('done', 'Done')],
        default='upload',
        required=True,
    )

    @api.onchange('batch_id')
    def _onchange_batch_id(self):
        if self.batch_id:
            self.client_id = self.batch_id.client_id
            self.period_start = self.batch_id.period_start
            self.period_end = self.batch_id.period_end
            self.journal_id = self.batch_id.journal_id
            self.analytic_account_id = self.batch_id.analytic_account_id

    def action_preview(self):
        """Parse the Excel file and populate preview lines with validation."""
        self.ensure_one()
        if not self.file:
            raise UserError(_('Please upload an Excel file.'))

        try:
            import openpyxl
        except ImportError:
            raise UserError(_('The openpyxl library is required. Please install it: pip install openpyxl'))

        file_data = base64.b64decode(self.file)
        try:
            workbook = openpyxl.load_workbook(io.BytesIO(file_data), data_only=True)
        except Exception as e:
            raise UserError(_('Could not open the Excel file: %s') % str(e))

        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            raise UserError(_('The Excel file is empty.'))

        # Parse headers from first row
        header_row = [str(cell).strip().lower() if cell else '' for cell in rows[0]]
        col_map = {}
        for col_idx, header in enumerate(header_row):
            if header in COLUMN_MAPPING:
                col_map[COLUMN_MAPPING[header]] = col_idx

        if 'name' not in col_map:
            raise UserError(
                _('Could not find the "Rider Name" or "Name" column in the Excel file. '
                  'Please ensure row 1 contains the column headers.\n\n'
                  'Found headers: %s') % ', '.join([h for h in header_row if h])
            )

        errors = []
        preview_vals = []

        for row_idx, row in enumerate(rows[1:], start=2):  # skip header
            def get_val(field, default=None):
                idx = col_map.get(field)
                if idx is None or idx >= len(row):
                    return default
                val = row[idx]
                return val if val is not None else default

            name = str(get_val('name', '')).strip()
            if not name:
                continue  # skip empty rows

            row_errors = []

            # Rider type
            raw_type = str(get_val('rider_type', '')).strip().lower()
            rider_type = RIDER_TYPE_MAPPING.get(raw_type, self.default_rider_type)

            # Numeric fields
            def parse_float(field_name, label):
                raw = get_val(field_name, 0)
                if raw is None or raw == '':
                    return 0.0
                try:
                    return float(raw)
                except (ValueError, TypeError):
                    row_errors.append(_('Row %d: "%s" has invalid numeric value: %s') % (row_idx, label, raw))
                    return 0.0

            fixed_salary = parse_float('fixed_salary', 'Fixed Salary')
            order_earnings = parse_float('order_earnings', 'Order Earnings')
            bonus = parse_float('bonus', 'Bonus')
            petrol = parse_float('petrol', 'Petrol')
            deduction = parse_float('deduction', 'Deduction')
            advance_deduction = parse_float('advance_deduction', 'Advance Deduction')
            fine = parse_float('fine', 'Fine')

            net_payable = fixed_salary + order_earnings + bonus + petrol - deduction - advance_deduction - fine
            if net_payable < 0:
                row_errors.append(
                    _('Row %d: Net payable for "%s" is negative (%.2f). Review deductions.') % (row_idx, name, net_payable)
                )

            employee_ref = str(get_val('employee_ref', '')).strip()
            vendor_ref = str(get_val('vendor_ref', '')).strip()
            note = str(get_val('note', '')).strip()

            errors.extend(row_errors)
            preview_vals.append({
                'wizard_id': self.id,
                'row_number': row_idx,
                'name': name,
                'rider_type': rider_type,
                'employee_ref': employee_ref,
                'vendor_ref': vendor_ref,
                'fixed_salary': fixed_salary,
                'order_earnings': order_earnings,
                'bonus': bonus,
                'petrol': petrol,
                'deduction': deduction,
                'advance_deduction': advance_deduction,
                'fine': fine,
                'net_payable': net_payable,
                'note': note,
                'has_error': bool(row_errors),
                'error_message': '\n'.join(row_errors),
            })

        # Clear previous preview lines
        self.preview_line_ids.unlink()
        if preview_vals:
            self.env['rider.import.preview.line'].create(preview_vals)

        self.error_log = '\n'.join(errors) if errors else False
        self.state = 'preview'

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_import(self):
        """Create the payroll batch and lines from the validated preview."""
        self.ensure_one()
        error_lines = self.preview_line_ids.filtered(lambda l: l.has_error)
        if error_lines:
            raise UserError(
                _('Please fix the %d error(s) before importing. '
                  'Review the Validation Errors section.') % len(error_lines)
            )
        if not self.preview_line_ids:
            raise UserError(_('No data to import. Please upload and preview the file first.'))

        # Get or create the batch
        batch = self.batch_id
        if not batch:
            if not self.client_id:
                raise UserError(_('Please select a Client when creating a new batch.'))
            if not self.journal_id:
                raise UserError(_('Please select a Payroll Journal when creating a new batch.'))
            company = self.env.company
            batch = self.env['rider.payroll.batch'].create({
                'client_id': self.client_id.id,
                'period_start': self.period_start,
                'period_end': self.period_end,
                'date': fields.Date.today(),
                'journal_id': self.journal_id.id,
                'analytic_account_id': self.analytic_account_id.id if self.analytic_account_id else False,
                'salary_account_id': company.rider_payroll_salary_account_id.id if company.rider_payroll_salary_account_id else False,
                'salary_payable_account_id': company.rider_payroll_salary_payable_account_id.id if company.rider_payroll_salary_payable_account_id else False,
                'state': 'draft',
            })

        # Resolve employees and vendors
        line_vals_list = []
        for pline in self.preview_line_ids:
            employee_id = False
            vendor_id = False

            if pline.rider_type == 'employee' and pline.employee_ref:
                employee = self.env['hr.employee'].search([
                    '|', ('name', 'ilike', pline.employee_ref),
                    ('barcode', '=', pline.employee_ref),
                    *self.env['hr.employee']._check_company_domain(batch.company_id),
                ], limit=1)
                if employee:
                    employee_id = employee.id

            if pline.rider_type == 'freelancer' and pline.vendor_ref:
                vendor = self.env['res.partner'].search([
                    ('name', 'ilike', pline.vendor_ref),
                ], limit=1)
                if vendor:
                    vendor_id = vendor.id

            line_vals_list.append({
                'batch_id': batch.id,
                'name': pline.name,
                'rider_type': pline.rider_type,
                'employee_id': employee_id,
                'vendor_id': vendor_id,
                'fixed_salary': pline.fixed_salary,
                'order_earnings': pline.order_earnings,
                'bonus': pline.bonus,
                'petrol': pline.petrol,
                'deduction': pline.deduction,
                'advance_deduction': pline.advance_deduction,
                'fine': pline.fine,
                'note': pline.note,
                'analytic_account_id': self.analytic_account_id.id if self.analytic_account_id else False,
                'state': 'draft',
            })

        self.env['rider.payroll.line'].create(line_vals_list)
        if batch.state == 'draft':
            batch.write({'state': 'imported'})

        return {
            'type': 'ir.actions.act_window',
            'name': _('Payroll Batch'),
            'res_model': 'rider.payroll.batch',
            'view_mode': 'form',
            'res_id': batch.id,
        }


class RiderImportPreviewLine(models.TransientModel):
    _name = 'rider.import.preview.line'
    _description = 'Rider Import Preview Line'
    _order = 'row_number'

    wizard_id = fields.Many2one(
        comodel_name='rider.import.wizard',
        required=True,
        ondelete='cascade',
    )
    row_number = fields.Integer(string='Row #')
    name = fields.Char(string='Rider Name')
    rider_type = fields.Selection(
        selection=[('employee', 'Employee'), ('freelancer', 'Freelancer')],
        string='Type',
    )
    employee_ref = fields.Char(string='Employee Ref')
    vendor_ref = fields.Char(string='Vendor Ref')
    fixed_salary = fields.Float(string='Fixed Salary', digits=(16, 2))
    order_earnings = fields.Float(string='Order Earnings', digits=(16, 2))
    bonus = fields.Float(string='Bonus', digits=(16, 2))
    petrol = fields.Float(string='Petrol', digits=(16, 2))
    deduction = fields.Float(string='Deduction', digits=(16, 2))
    advance_deduction = fields.Float(string='Advance', digits=(16, 2))
    fine = fields.Float(string='Fine', digits=(16, 2))
    net_payable = fields.Float(string='Net Payable', digits=(16, 2))
    note = fields.Char(string='Note')
    has_error = fields.Boolean(string='Has Error')
    error_message = fields.Text(string='Error')
