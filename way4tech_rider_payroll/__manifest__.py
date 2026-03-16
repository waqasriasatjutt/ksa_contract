# -*- coding: utf-8 -*-
{
    'name': 'Rider Payroll Automation',
    'version': '19.0.1.0.0',
    'summary': 'Import and process rider salary sheets from Excel for HungerStation and delivery platforms',
    'description': """
Rider Payroll Automation
========================
This module automates rider payroll processing for logistics and delivery companies:

* Import rider salary sheets from Excel (.xlsx)
* Data validation and error reporting during import
* Auto-classification: Company Riders → Payslip Journal Entry | Freelancers → Vendor Bill
* Handles: fixed salary, order-based earnings, bonuses, deductions, petrol, advances, fines
* Net payable calculation per rider
* Analytic tagging per client (e.g., HungerStation)
* Automatic accounting entries (journal entries and vendor bills)
* Batch payroll management with state workflow
    """,
    'category': 'Human Resources/Payroll',
    'author': 'Way4Tech',
    'website': 'https://way4tech.com',
    'license': 'LGPL-3',
    'depends': ['base', 'account', 'hr', 'analytic', 'mail', 'hr_payroll'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'data/res_config_settings_data.xml',
        'views/rider_payroll_batch_views.xml',
        'views/rider_payroll_line_views.xml',
        'views/res_config_settings_views.xml',
        'wizard/rider_import_wizard_views.xml',
        'report/rider_payroll_report.xml',
        'report/rider_payroll_report_template.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
}
