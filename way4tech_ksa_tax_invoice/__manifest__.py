# -*- coding: utf-8 -*-
{
    'name': 'KSA Bilingual Tax Invoice (Al Zain format)',
    'version': '19.0.3.1.0',
    'category': 'Accounting',
    'summary': 'Bilingual Arabic/English ZATCA-style Tax Invoice PDF + shared '
               'ATCO bilingual letterhead applied to invoice/SO/PO/etc. reports. '
               'Data-driven from the company + partner + invoice.',
    'author': 'Way4Tech',
    'license': 'LGPL-3',
    'depends': ['account', 'l10n_sa', 'way4tech_logistics'],
    'data': [
        'views/res_company_views.xml',
        'report/paperformat.xml',
        'report/external_layout.xml',
        'report/report_actions.xml',
        'report/tax_invoice_report.xml',
        'data/ksa_atco_setup.xml',
    ],
    'installable': True,
    'application': False,
}
