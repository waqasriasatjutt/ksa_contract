import base64
import io
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
except ImportError:
    openpyxl = None
    _logger.warning(
        'openpyxl not found. Fleet Excel export will not work. '
        'Install with: pip install openpyxl'
    )


class FleetExcelExport(models.TransientModel):
    _name = 'way4tech.fleet.excel.export'
    _description = 'Fleet Excel Export Wizard'

    file_data = fields.Binary(string='Excel File', readonly=True)
    file_name = fields.Char(string='File Name', readonly=True)

    def action_export(self):
        self.ensure_one()
        if not openpyxl:
            raise UserError(_(
                'openpyxl is required. Install with: pip install openpyxl'
            ))

        vehicles = self.env['fleet.vehicle'].search([])
        if not vehicles:
            raise UserError(_('No fleet vehicles to export.'))

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Fleet Master Data'

        headers = [
            'Fleet Sequence #', 'License Plate', 'Chassis #',
            'Plate Type', 'Vehicle Category', 'Model', 'Model Year',
            'Ownership Type', 'Investor', 'Profit Share %',
            'Operational State', 'Purchase Value',
            'Registration Expiry', 'Inspection Expiry',
            'Insurance Expiry', 'Operation Card Expiry',
            'Current Driver', 'Driver Iqama #', 'Handover Date',
            'Current Client', 'Analytic Account',
            'Is Installment', 'Financing Vendor',
            'Total Financed', 'Monthly Installment',
            'Installments Paid', 'Outstanding Balance',
            'PO Limit per Trip', 'Company',
        ]

        # Header row styling
        header_fill = PatternFill(start_color='FFD700', end_color='FFD700', fill_type='solid')
        header_font = Font(bold=True)
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=1, column=col_idx, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)

        row_idx = 2
        for v in vehicles:
            ws.cell(row=row_idx, column=1, value=v.way4tech_sequence or '')
            ws.cell(row=row_idx, column=2, value=v.license_plate or '')
            ws.cell(row=row_idx, column=3, value=v.chassis_number or '')
            ws.cell(row=row_idx, column=4, value=dict(v._fields['plate_type'].selection).get(v.plate_type, '') if v.plate_type else '')
            ws.cell(row=row_idx, column=5, value=dict(v._fields['vehicle_category'].selection).get(v.vehicle_category, '') if v.vehicle_category else '')
            ws.cell(row=row_idx, column=6, value=v.model_id.display_name if v.model_id else '')
            ws.cell(row=row_idx, column=7, value=v.model_year or '')
            ws.cell(row=row_idx, column=8, value=dict(v._fields['ownership_type'].selection).get(v.ownership_type, '') if v.ownership_type else '')
            ws.cell(row=row_idx, column=9, value=v.investor_id.name if v.investor_id else '')
            ws.cell(row=row_idx, column=10, value=float(v.profit_share_rate or 0.0))
            ws.cell(row=row_idx, column=11, value=dict(v._fields['operational_state'].selection).get(v.operational_state, '') if v.operational_state else '')
            ws.cell(row=row_idx, column=12, value=float(v.purchase_value or 0.0))
            ws.cell(row=row_idx, column=13, value=v.registration_expiry_date)
            ws.cell(row=row_idx, column=14, value=v.inspection_expiry_date)
            ws.cell(row=row_idx, column=15, value=v.insurance_expiry_date)
            ws.cell(row=row_idx, column=16, value=v.operation_card_expiry_date)
            ws.cell(row=row_idx, column=17, value=v.current_driver_name or '')
            ws.cell(row=row_idx, column=18, value=v.current_driver_iqama or '')
            ws.cell(row=row_idx, column=19, value=v.current_driver_handover_date)
            ws.cell(row=row_idx, column=20, value=v.current_client_id.name if v.current_client_id else '')
            ws.cell(row=row_idx, column=21, value=v.analytic_account_id.name if v.analytic_account_id else '')
            ws.cell(row=row_idx, column=22, value='Yes' if v.is_installment else 'No')
            ws.cell(row=row_idx, column=23, value=v.installment_vendor_id.name if v.installment_vendor_id else '')
            ws.cell(row=row_idx, column=24, value=float(v.installment_total_price or 0.0))
            ws.cell(row=row_idx, column=25, value=float(v.installment_monthly_amount or 0.0))
            ws.cell(row=row_idx, column=26, value=v.installments_paid or 0)
            ws.cell(row=row_idx, column=27, value=float(v.installment_remaining_balance or 0.0))
            ws.cell(row=row_idx, column=28, value=float(v.po_limit or 0.0))
            ws.cell(row=row_idx, column=29, value=v.company_id.name if v.company_id else '')
            row_idx += 1

        # Auto-size columns (approximate)
        for col_idx in range(1, len(headers) + 1):
            column_letter = openpyxl.utils.get_column_letter(col_idx)
            ws.column_dimensions[column_letter].width = 18

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        file_content = output.read()
        output.close()

        self.write({
            'file_data': base64.b64encode(file_content),
            'file_name': 'fleet_master_data.xlsx',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/?model=way4tech.fleet.excel.export&id=%d&field=file_data&filename_field=file_name&download=true' % self.id,
            'target': 'self',
        }
