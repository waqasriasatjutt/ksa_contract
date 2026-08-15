# -*- coding: utf-8 -*-
"""CR7 item 1 (19.0.3.13.0) — combined, READ-ONLY Project Expenses report.

The Project Expenses screen (action-1394) historically listed only
``way4tech.manpower.project.expense`` rows. Sales Person Commission lives on a
separate model (``way4tech.manpower.commission.line``) and so never appeared
there, even though it is a project cost the client expects to see alongside
Worker Wages, Fuel, Refreshment, Client Commission, etc.

This model is a pure SQL ``VIEW`` (``_auto = False``) that UNIONs the two source
tables into one read-only list/pivot. It writes nothing and duplicates nothing —
each row is a live projection of an existing source record. The commission rows
carry a constant Category label of "Sales Person Commission" so group-by
Client / Category keeps working and the commission surfaces as its own group.

Design / safety notes
---------------------
- Additive only. Neither source model, nor its creation/billing logic, is
  touched. Editing still happens on the contract's own notebook tabs.
- Read-only by construction (a DB view has no INSERT/UPDATE). The list/pivot/
  form also set create/edit/delete = false as belt-and-suspenders.
- Stable synthetic ``id``: expense rows use ``id*2`` (even), commission rows use
  ``id*2+1`` (odd). Two independent sequences, so no collision, and the mapping
  is stable across view refreshes. ``res_id`` keeps the real source id.
- Core Accounting is not involved at all — this reads only the module's own
  manpower tables (plus the contract for client / analytic, and the category
  for its translated name).
"""
from odoo import fields, models, tools


class ManpowerProjectExpenseReport(models.Model):
    _name = 'way4tech.manpower.project.expense.report'
    _description = 'Project Expenses (incl. Sales Person Commission)'
    _auto = False
    _order = 'date desc, id desc'
    _rec_name = 'description'

    # Which source model a row projects: 'expense' or 'commission'. Drives the
    # "Open Contract" button and the commission-only search filter.
    source_model = fields.Char(string='Source', readonly=True)
    res_id = fields.Integer(string='Source Record ID', readonly=True)

    contract_id = fields.Many2one(
        'way4tech.manpower.contract', string='Contract', readonly=True)
    client_id = fields.Many2one('res.partner', string='Client', readonly=True)
    # Char (not the m2o category_id) so both sources share one group-by axis:
    # the expense category name for expense rows, the constant
    # "Sales Person Commission" for commission rows.
    category = fields.Char(string='Category', readonly=True)
    employee_id = fields.Many2one(
        'hr.employee', string='Salesperson', readonly=True,
        help='Set on Sales Person Commission rows only.')
    date = fields.Date(string='Accounting Date', readonly=True)
    description = fields.Char(string='Description', readonly=True)
    vendor_id = fields.Many2one('res.partner', string='Vendor', readonly=True)
    account_id = fields.Many2one(
        'account.account', string='Expense Account', readonly=True)
    amount = fields.Monetary(
        string='Amount', currency_field='currency_id', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', readonly=True)
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Analytic Account', readonly=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('invoice_draft', 'Bill Draft'),
         ('billed', 'Bill Created')],
        string='Status', readonly=True)
    bill_id = fields.Many2one('account.move', string='Vendor Bill', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW %s AS (
                SELECT
                    (pe.id * 2)                                   AS id,
                    'expense'                                     AS source_model,
                    pe.id                                         AS res_id,
                    pe.contract_id                                AS contract_id,
                    pe.client_id                                  AS client_id,
                    COALESCE(cat.name ->> 'en_US', cat.name::text) AS category,
                    NULL::integer                                 AS employee_id,
                    pe.date                                       AS date,
                    pe.description                                AS description,
                    pe.vendor_id                                  AS vendor_id,
                    pe.account_id                                 AS account_id,
                    pe.amount                                     AS amount,
                    pe.currency_id                                AS currency_id,
                    pe.company_id                                 AS company_id,
                    pe.analytic_account_id                        AS analytic_account_id,
                    pe.state                                      AS state,
                    pe.bill_id                                    AS bill_id
                FROM way4tech_manpower_project_expense pe
                LEFT JOIN way4tech_expense_category cat ON cat.id = pe.category_id

                UNION ALL

                SELECT
                    (cl.id * 2 + 1)                               AS id,
                    'commission'                                  AS source_model,
                    cl.id                                         AS res_id,
                    cl.contract_id                                AS contract_id,
                    c.client_id                                   AS client_id,
                    'Sales Person Commission'                     AS category,
                    cl.employee_id                                AS employee_id,
                    cl.date                                       AS date,
                    cl.description                                AS description,
                    cl.vendor_id                                  AS vendor_id,
                    cl.account_id                                 AS account_id,
                    cl.amount                                     AS amount,
                    cl.currency_id                                AS currency_id,
                    cl.company_id                                 AS company_id,
                    c.analytic_account_id                         AS analytic_account_id,
                    cl.state                                      AS state,
                    cl.bill_id                                    AS bill_id
                FROM way4tech_manpower_commission_line cl
                LEFT JOIN way4tech_manpower_contract c ON c.id = cl.contract_id
            )
        """ % self._table)

    def action_open_contract(self):
        """Read-only convenience: jump to the parent contract to view/edit the
        underlying line (creation/editing lives on the contract, never here)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.contract_id.display_name,
            'res_model': 'way4tech.manpower.contract',
            'res_id': self.contract_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
