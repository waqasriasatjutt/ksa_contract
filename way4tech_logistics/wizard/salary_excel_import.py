import base64
import io
import logging

import re

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import openpyxl
except ImportError:
    openpyxl = None
    _logger.warning(
        'openpyxl library not found. Excel import functionality will not work. '
        'Install it with: pip install openpyxl'
    )

# ─────────────────────────────────────────────────────────────────────────────
# Expected Excel column order (row 1 = headers, row 2+ = data):
#
#  A  Employee Name          (required)
#  B  Platform               name — looked up in way4tech.platform.config
#  C  Valid Days             integer
#  D  Orders Completed       integer
#  E  Fixed Salary           float  (auto-computed if platform set; manual override ok)
#  F  Order Adjustment       float  (positive=bonus, negative=deduction; auto if platform)
#  G  Bonus                  float
#  H  Petrol Allowance       float
#  I  On-Time Deduction      float
#  J  Food Damage Deduction  float
#  K  Miss Day Penalty       float
#  L  Order Rejection Ded.   float
#  M  Misc Deduction         float
#  N  Advance                float
#  O  Fuel                   float
#  P  SIM Charges            float
#  Q  Loan                   float
#  R  Traffic Violation      float
#  S  Rent                   float
#  T  Note                   text
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# 2026-10-08: the one place the import format is written down.
#
# The template, the instructions on the popup and the reader below are all built
# from this list, so they cannot say different things again. They used to: the
# popup advertised 21 columns beginning with a "Rider Type" that no field in the
# system has ever held, which pushed every letter after it along by one, so a
# sheet filled in as the popup described put the salary into Order Adjustment.
#
# field    - where the value lands on a salary line
# label    - the header written into the template and shown on the popup
# kind     - how the cell is read
# aliases  - headers from earlier sheets that mean the same column, so a file
#            somebody already filled in still imports correctly
COLUMNS = [
    ('employee_name', 'Employee Name', 'text', ('name', 'rider name')),
    ('platform_id', 'Platform', 'platform', ('platform name',)),
    ('valid_days', 'Valid Days', 'int', ('days',)),
    ('orders_completed', 'Orders Completed', 'int', ('orders',)),
    ('fixed_salary', 'Basic Salary', 'money', ('fixed salary', 'basic/fixed salary')),
    ('order_adjustment', 'Order Adjustment', 'money', ('other adjustments',)),
    ('bonus', 'Bonus', 'money', ()),
    ('petrol_allowance', 'Petrol Allowance', 'money', ('petrol',)),
    ('on_time_deduction', 'On-Time Deduction', 'money', ('on time deduction',)),
    ('food_damage_deduction', 'Food Damage Deduction', 'money', ('food damage',)),
    ('miss_day_penalty', 'Miss Day Penalty', 'money', ('miss day',)),
    ('order_rejection_deduction', 'Order Rejection Deduction', 'money', ('order rejection',)),
    ('misc_deduction', 'Misc Deduction', 'money', ('misc',)),
    ('advance_deduction', 'Advance', 'money', ('advance deduction',)),
    ('fuel_deduction', 'Fuel', 'money', ('fuel deduction',)),
    ('sim_charges', 'SIM Charges', 'money', ('sim',)),
    ('loan', 'Loan Installment', 'money', ('loan',)),
    ('traffic_violation', 'Traffic Violation', 'money', ('traffic',)),
    ('rent', 'Rent', 'money', ()),
    ('note', 'Note', 'text', ('remarks',)),
]

COLUMN_NOTES = {
    'employee_name': 'Required. The employee must already exist in Employees; '
                     'a line whose name is not found is skipped and listed back to you.',
    'platform_id': 'Platform name (Hungerstation, Keeta...). Fills the salary '
                   'from the platform rules when Basic Salary is left blank.',
    'valid_days': 'Whole number. Used by the platform rules.',
    'orders_completed': 'Whole number. Used by the platform rules.',
    'fixed_salary': 'Always fills Basic Salary, with or without a platform. '
                    'Leave blank to let the platform rules work it out.',
    'order_adjustment': 'Positive adds, negative deducts. Filled by the platform '
                        'rules only when Basic Salary is blank.',
    'note': 'Free text, kept on the line.',
}


def _column_letter(index):
    """0 -> A, 25 -> Z, 26 -> AA."""
    letters = ''
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        letters = chr(65 + rest) + letters
    return letters


def _normalise(header):
    return re.sub(r'[^a-z0-9]+', ' ', (header or '').strip().lower()).strip()



class SalaryExcelImport(models.TransientModel):
    _name = 'way4tech.salary.excel.import'
    _description = 'Salary Excel Import Wizard'

    import_id = fields.Many2one(
        comodel_name='way4tech.salary.import',
        string='Salary Import',
        required=True,
    )
    excel_file = fields.Binary(
        string='Excel File (.xlsx)',
        required=True,
    )
    file_name = fields.Char(string='File Name')
    format_html = fields.Html(
        string='Expected Format', compute='_compute_format_html', sanitize=False,
        help='Built from the same definition as the template, so what is shown '
             'here and what the file contains can never disagree.')

    def _compute_format_html(self):
        rows = []
        for position, (field, label, kind, aliases) in enumerate(COLUMNS):
            rows.append(
                '<tr><td style="padding:2px 6px"><strong>%s</strong></td>'
                '<td style="padding:2px 6px">%s</td>'
                '<td style="padding:2px 6px">%s</td></tr>' % (
                    _column_letter(position), label,
                    COLUMN_NOTES.get(field, '')))
        table = (
            '<p class="mb-1"><strong>Expected format: %s columns (A to %s), '
            'row 1 = header, data from row 2.</strong> Download the template '
            'below and fill it in; the headers in it are exactly these, in this '
            'order.</p>'
            '<table style="width:100%%;font-size:12px;border-collapse:collapse">'
            '<tr style="background:#d9edf7">'
            '<th style="padding:2px 6px;text-align:left">Col</th>'
            '<th style="padding:2px 6px;text-align:left">Field</th>'
            '<th style="padding:2px 6px;text-align:left">Notes</th></tr>'
            '%s</table>') % (
                len(COLUMNS), _column_letter(len(COLUMNS) - 1), ''.join(rows))
        for record in self:
            record.format_html = table

    def action_import(self):
        self.ensure_one()

        if not openpyxl:
            raise UserError(_(
                'The openpyxl Python library is required for Excel import. '
                'Please install it: pip install openpyxl'
            ))
        if not self.excel_file:
            raise UserError(_('Please select an Excel file to import.'))

        try:
            file_data = base64.b64decode(self.excel_file)
        except Exception as e:
            raise UserError(_('Could not decode the file: %s') % str(e))

        try:
            workbook = openpyxl.load_workbook(
                filename=io.BytesIO(file_data), read_only=True, data_only=True
            )
        except Exception as e:
            raise UserError(_(
                'Could not open the Excel file. Please make sure it is a valid .xlsx file.\n'
                'Error: %s'
            ) % str(e))

        sheet = workbook.active

        def to_float(val):
            if val is None or val == '':
                return 0.0
            try:
                return float(val)
            except (ValueError, TypeError):
                return 0.0

        def to_int(val):
            if val is None or val == '':
                return 0
            try:
                return int(float(val))
            except (ValueError, TypeError):
                return 0

        def to_str(val):
            if val is None:
                return ''
            return str(val).strip()

        import_id = self.import_id
        default_platform = import_id.platform_id

        # Cache: platform name (lower) → way4tech.platform.config record
        platform_cache = {}

        def get_platform(name_raw):
            if not name_raw:
                return default_platform
            key = name_raw.strip().lower()
            if key not in platform_cache:
                rec = self.env['way4tech.platform.config'].search(
                    [('name', 'ilike', name_raw.strip())], limit=1
                )
                platform_cache[key] = rec
            return platform_cache[key]

        # 2026-10-08: the sheet is read by its headers. A column that has been
        # moved, or a header from an earlier version of the template, still
        # lands in the right field; only a header we cannot place at all falls
        # back to its position in the published format.
        header_row = next(sheet.iter_rows(min_row=1, max_row=1, values_only=True), ())
        seen = {}
        for position, cell in enumerate(header_row):
            key = _normalise(cell if isinstance(cell, str) else '')
            if key:
                seen.setdefault(key, position)
        index_of = {}
        for position, (field, label, kind, aliases) in enumerate(COLUMNS):
            found = seen.get(_normalise(label))
            if found is None:
                for alias in aliases:
                    found = seen.get(_normalise(alias))
                    if found is not None:
                        break
            index_of[field] = position if found is None else found

        readers = {'text': to_str, 'platform': to_str, 'int': to_int, 'money': to_float}

        def read_row(row):
            out = {}
            for field, label, kind, aliases in COLUMNS:
                position = index_of[field]
                raw = row[position] if len(row) > position else None
                out[field] = readers[kind](raw)
            return out

        lines_to_create = []
        names_not_found = []

        for row_index, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            if not any(cell for cell in row):
                continue

            values = read_row(row)
            employee_name = values['employee_name']
            if not employee_name:
                continue
            platform = get_platform(values['platform_id'])
            valid_days = values['valid_days']
            orders_completed = values['orders_completed']
            fixed_salary = values['fixed_salary']
            order_adjustment = values['order_adjustment']
            bonus = values['bonus']
            petrol_allowance = values['petrol_allowance']
            on_time_deduction = values['on_time_deduction']
            food_damage_deduction = values['food_damage_deduction']
            miss_day_penalty = values['miss_day_penalty']
            order_rejection_deduction = values['order_rejection_deduction']
            misc_deduction = values['misc_deduction']
            advance_deduction = values['advance_deduction']
            fuel_deduction = values['fuel_deduction']
            sim_charges = values['sim_charges']
            loan = values['loan']
            traffic_violation = values['traffic_violation']
            rent = values['rent']
            note = values['note']

            # Look up the employee's current outstanding loan balance for display
            loan_balance_before = 0.0

            # Auto-compute salary from platform rules if platform found
            # and fixed_salary was NOT explicitly provided in the file
            if platform and not fixed_salary and (valid_days or orders_completed):
                fixed_salary, order_adjustment = platform.compute_salary(
                    valid_days, orders_completed
                )

            # Try to find employee by name
            employee = self.env['hr.employee'].search(
                [('name', 'ilike', employee_name)], limit=1
            )

            line_vals = {
                'import_id': import_id.id,
                'sequence': row_index - 1,
                'employee_name': employee_name,
                'platform_id': platform.id if platform else False,
                'valid_days': valid_days,
                'orders_completed': orders_completed,
                'fixed_salary': fixed_salary,
                'order_adjustment': order_adjustment,
                'bonus': bonus,
                'petrol_allowance': petrol_allowance,
                'on_time_deduction': on_time_deduction,
                'food_damage_deduction': food_damage_deduction,
                'miss_day_penalty': miss_day_penalty,
                'order_rejection_deduction': order_rejection_deduction,
                'misc_deduction': misc_deduction,
                'advance_deduction': advance_deduction,
                'fuel_deduction': fuel_deduction,
                'sim_charges': sim_charges,
                'loan': loan,
                'loan_balance_before': loan_balance_before,
                'traffic_violation': traffic_violation,
                'rent': rent,
                'note': note,
                'has_error': False,
                'error_message': '',
            }

            if employee:
                line_vals['employee_id'] = employee.id
                # Look up outstanding loan balance for this employee
                loan_deductions = self.env['way4tech.employee.deduction'].search([
                    ('state', '=', 'posted'),
                    ('outstanding', '>', 0),
                    ('employee_id', '=', employee.id),
                    ('deduction_type', '=', 'loan'),
                ])
                line_vals['loan_balance_before'] = sum(
                    d.amount - d.recovered_amount for d in loan_deductions
                )
            else:
                # 2026-10-08: no employee is created by an import. A misspelt
                # name used to become a second employee record, and payroll then
                # ran twice for one person. The line is left out and the name is
                # reported, so it can be created in Employees and imported again.
                names_not_found.append(employee_name)
                continue

            lines_to_create.append(line_vals)

        if not lines_to_create:
            if names_not_found:
                raise UserError(_(
                    'None of the names in this file match an employee, so '
                    'nothing was imported.\n\nCreate these in Employees first, '
                    'then import the file again:\n\n%s'
                ) % '\n'.join('  - %s' % name for name in names_not_found))
            raise UserError(_(
                'No data rows found in the Excel file. '
                'Make sure the file has data starting from row 2.'
            ))

        # Remove existing lines before importing new ones
        import_id.line_ids.unlink()

        # Create all lines
        self.env['way4tech.salary.import.line'].create(lines_to_create)

        import_id.state = 'imported'

        if names_not_found:
            # Imported what matched and said plainly what did not, rather than
            # inventing an employee for a name nobody recognises.
            import_id.message_post(body=_(
                '<p>%(count)s line(s) were left out: no employee of that name '
                'exists. Create them in Employees and import the file again.</p>'
                '<ul>%(names)s</ul>'
            ) % {
                'count': len(names_not_found),
                'names': ''.join('<li>%s</li>' % name
                                 for name in names_not_found),
            })
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'type': 'warning',
                    'title': _('Imported with %s line(s) left out')
                             % len(names_not_found),
                    'message': _(
                        'No employee matches: %(names)s.\nCreate them in '
                        'Employees and import the file again. The names are '
                        'also in this import\'s message history.'
                    ) % {'names': ', '.join(names_not_found[:8])
                         + (', ...' if len(names_not_found) > 8 else '')},
                    'sticky': True,
                    'next': {'type': 'ir.actions.act_window_close'},
                },
            }

        return {'type': 'ir.actions.act_window_close'}

    @api.model
    def action_download_template(self):
        """Generate and return a sample salary import XLSX template."""
        if not openpyxl:
            raise UserError(_(
                'The openpyxl Python library is required. '
                'Install it with: pip install openpyxl'
            ))

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Salary Import'

        from openpyxl.styles import Font, PatternFill, Alignment
        header_font = Font(bold=True, color='FFFFFF')
        header_fill = PatternFill(start_color='1F4E79', end_color='1F4E79', fill_type='solid')

        headers = [label for _f, label, _k, _a in COLUMNS]
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')

        # A few rows showing how it is filled in. Basic Salary left blank on the
        # platform lines, so the platform rules fill it; typed in on the last
        # line, which is how a rider on a fixed wage is paid.
        sample_rows = [
            ['Ahmed Al-Rashidi', 'Hungerstation', 27, 310, '', '', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 500, 0, 0, ''],
            ['Mohammed Al-Zahrani', 'Hungerstation', 25, 280, '', '', 0, 0, 10, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, ''],
            ['Omar Al-Harthi', 'Keeta', 26, 290, '', '', 0, 0, 0, 5, 0, 0, 0, 200, 0, 50, 0, 0, 0, ''],
            ['Faisal Al-Qahtani', 'Keeta', 27, 320, '', '', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1000, 0, 0, 'Loan total 3000'],
            ['Saad Al-Dosari', '', 0, 0, 3500, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 'Fixed wage, no platform'],
        ]
        for row_data in sample_rows:
            ws.append(row_data)

        for col, (_field, label, _kind, _aliases) in enumerate(COLUMNS, 1):
            ws.column_dimensions[
                ws.cell(row=1, column=col).column_letter].width = max(10, len(label) + 4)

        # Write to bytes
        import io as _io
        output = _io.BytesIO()
        wb.save(output)
        output.seek(0)

        import base64 as _b64
        file_data = _b64.b64encode(output.read()).decode()

        # Return as file download attachment
        attachment = self.env['ir.attachment'].create({
            'name': 'salary_import_template.xlsx',
            'type': 'binary',
            'datas': file_data,
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d?download=true' % attachment.id,
            'target': 'new',
        }
