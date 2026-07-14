# -*- coding: utf-8 -*-
{
    'name': 'KSA Localization (Tax Invoice, Letterhead, Bilingual Contacts)',
    'version': '19.0.5.3.0',
    'category': 'Accounting',
    'summary': 'KSA localization pack: bilingual Arabic/English tax invoice PDF, '
               'shared ATCO letterhead for all reports, Arabic address fields on '
               'contacts + companies, KSA-standard DD/MM/YYYY date format.',
    'author': 'Way4Tech',
    'license': 'LGPL-3',
    'depends': ['account', 'l10n_sa', 'way4tech_logistics'],
    'data': [
        'views/res_company_views.xml',
        'views/res_partner_views.xml',
        'report/paperformat.xml',
        'report/external_layout.xml',
        'report/report_actions.xml',
        'report/tax_invoice_report.xml',
        'data/ksa_atco_setup.xml',
    ],
    'installable': True,
    'application': False,
}
