# -*- coding: utf-8 -*-
"""CB1 (19.0.4.0.0) — wire the three new Commissioning config slots.

For every payroll.settings, fill ONLY the new blank Commissioning fields from
the known Commissioning account/journal codes in that company. Touches nothing
else; never overwrites a value already set.
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Account = env['account.account']
    Journal = env['account.journal']
    for st in env['way4tech.payroll.settings'].search([]):
        company = st.company_id
        vals = {}
        if not st.commissioning_payable_account_id:
            acc = Account.search([('code', '=', '210002'),
                                  ('company_ids', 'in', company.id)], limit=1)
            if acc:
                vals['commissioning_payable_account_id'] = acc.id
        if not st.subcontractor_advance_account_id:
            acc = Account.search([('code', '=', '142005'),
                                  ('company_ids', 'in', company.id)], limit=1)
            if acc:
                vals['subcontractor_advance_account_id'] = acc.id
        if not st.commissioning_purchase_journal_id:
            j = Journal.search([('type', '=', 'purchase'),
                                ('company_id', '=', company.id),
                                ('name', 'ilike', 'commission')], limit=1)
            if j:
                vals['commissioning_purchase_journal_id'] = j.id
        if vals:
            st.write(vals)
