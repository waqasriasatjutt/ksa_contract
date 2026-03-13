# -*- coding: utf-8 -*-
{
    'name': 'Commission-Based Invoicing',
    'version': '19.0.1.0.0',
    'summary': 'Record full customer receipts as liability, auto-calculate commission, generate commission invoices',
    'description': """
Commission-Based Invoicing
==========================
Designed for logistics and delivery companies that act as intermediaries:

* Record full customer receipts as liability (trust account)
* Automatic commission calculation (configurable % applied after VAT exclusion)
* Commission invoice generation with VAT applied only on commission portion
* Subcontractor payable balance tracking
* Commission reporting: daily, monthly, yearly
* Analytic tagging per client/project
* KSA VAT compliant – VAT only on the commission portion

Workflow:
1. Create Receipt → full amount recorded as customer deposit liability
2. Confirm → journal entry: Dr Cash/Bank | Cr Customer Deposits
3. Generate Commission Invoice → customer invoice for commission + VAT
4. Settle → clear liability: commission to income, balance to subcontractor payable
    """,
    'category': 'Accounting/Accounting',
    'author': 'Way4Tech',
    'website': 'https://way4tech.com',
    'license': 'LGPL-3',
    'depends': ['base', 'account', 'analytic', 'mail'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/sequence_data.xml',
        'views/commission_receipt_views.xml',
        'views/res_config_settings_views.xml',
        'report/commission_report.xml',
        'report/commission_report_template.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
}
