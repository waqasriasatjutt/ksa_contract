# -*- coding: utf-8 -*-
{
    'name': 'KSA Bilingual Tax Invoice (Al Zain format)',
    'version': '19.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Bilingual Arabic/English ZATCA-style Tax Invoice PDF matching '
               'the Al Zain Tower layout (seller/buyer grids, bilingual line '
               'table, VAT totals, amount in words, ZATCA QR, payee/bank block). '
               'Data-driven from the company + partner + invoice.',
    'author': 'Way4Tech',
    'license': 'LGPL-3',
    'depends': ['account', 'l10n_sa', 'way4tech_logistics'],
    'data': [
        'report/paperformat.xml',
        'report/report_actions.xml',
        'report/tax_invoice_report.xml',
    ],
    'installable': True,
    'application': False,
}
