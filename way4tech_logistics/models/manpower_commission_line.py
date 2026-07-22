# -*- coding: utf-8 -*-
"""CR2 G3 (19.0.2.7.0) — Sales Person Commission notebook line on a
manpower contract.

One row per commission payout. Amount auto-computes via the parent
contract's ``_get_commission_amount(employee, date)`` helper — which
honours the contract's ``commission_type`` and the per-employee
template rate (way4tech.commission.template). Percentage modes are
gated on ``pp_actual_profit > 0`` (no profit → no commission).

Once billed, the created vendor bill is stored on ``bill_id`` and the
state locks the line — subsequent recompute cycles SKIP billed lines
so the amount stays in sync with what actually posted to the GL
(skeptic bug 3/4 fix).

Design notes
------------
- ``date`` and ``bill_month`` are declared WITHOUT ``tracking=True``.
  Direct lesson from the CR2 G2 project_expense date-picker loop.
- ``bill_month`` is a non-stored Char compute (same pattern as
  inv_month on the income line, month on the budget line) and is
  hidden from the list via ``column_invisible=1`` to avoid the
  neighbour-cell re-render variant of the same loop.
- ``_get_commission_amount`` never calls ``message_post`` (skeptic
  bug 1 fix) — it uses ``_logger.warning`` for missing templates
  and defers user-facing errors to ``action_create_bill``.
"""
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class Way4TechManpowerCommissionLine(models.Model):
    _name = 'way4tech.manpower.commission.line'
    _description = 'Manpower Contract — Sales Person Commission Line'
    _inherit = ['way4tech.manpower.approval.mixin']
    # date dropped from _order — sort by editable date in inline lists
    # re-orders rows on every pick → picker loop. See income-line comment.
    _order = 'id desc'

    contract_id = fields.Many2one(
        'way4tech.manpower.contract', required=True, ondelete='cascade',
    )
    company_id = fields.Many2one(related='contract_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one(related='contract_id.currency_id', store=True, readonly=True)

    date = fields.Date(
        string='Accounting Date', required=True, default=fields.Date.context_today,
        help='Posting date on the generated vendor bill (account.move.date).',
    )
    bill_month = fields.Char(
        string='Bill Month (Auto)',
        compute='_compute_bill_month',
        help='%m/%Y derived from Accounting Date. Non-stored on purpose — '
             'writing a DB column on every date pick would trigger the '
             'editable-list picker-loop (see CR2 G2 date-picker lesson).',
    )
    expense_type = fields.Char(
        string='Expense Type', readonly=True, default='Sales Person Commission',
        help='Constant label — every line on this tab is a sales-person '
             'commission expense.',
    )
    tag_ids = fields.Many2many(
        'way4tech.tag',
        'way4tech_commission_line_tag_rel',
        'line_id', 'tag_id',
        string='Contract Tags',
    )
    employee_id = fields.Many2one(
        'hr.employee', string='Salesperson', required=True,
        default=lambda self: self._default_employee_id(),
        help='Salesperson receiving the commission. Defaults from the '
             "contract's Salesperson field via context on the notebook tab. "
             'Rate is looked up on way4tech.commission.template by employee.',
    )
    description = fields.Char(string='Description')
    vendor_id = fields.Many2one(
        'res.partner', string='Vendor',
        compute='_compute_vendor_id', store=True, readonly=False,
        help='Payee on the generated vendor bill. Auto-resolves from the '
             "employee's linked user (user_id.partner_id) or Work Contact "
             '(work_contact_id) but is editable. Re-resolves on every '
             'employee_id change so swapping the salesperson updates the '
             'vendor accordingly (skeptic bug 5 fix).',
    )
    account_id = fields.Many2one(
        'account.account', string='Expense Account', check_company=True,
        default=lambda self: self._default_account_id(),
        help='GL expense account debited on the vendor bill. Defaults from '
             'Payroll & Accounting Setup → Sales Person Commission Rules → '
             'Commission Expense Account.',
    )
    amount = fields.Monetary(
        string='Amount', currency_field='currency_id',
        compute='_compute_amount', store=True, readonly=False,
        help="Auto-computed via contract._get_commission_amount() using the "
             "contract's commission_type + the employee's template rate. "
             'Editable — accountant can override before posting the bill. '
             'FROZEN once state=\"billed\" so the amount cannot drift from '
             'the GL when downstream profit shifts (skeptic bug 3 fix).',
    )
    bill_id = fields.Many2one(
        'account.move', string='Vendor Bill', readonly=True, copy=False,
    )
    # CR2 G4 amendment A: pin specific bill line for per-line sync-back.
    bill_line_id = fields.Many2one(
        'account.move.line',
        string='Bill Line',
        readonly=True, copy=False, ondelete='set null',
        help='CR2 G4: the account.move.line minted by Create Bill on this '
             'commission row. Sync back-reads price_subtotal from this line.',
    )
    state = fields.Selection(
        [('draft', 'Draft'), ('billed', 'Bill Created')],
        default='draft', readonly=True, copy=False,
    )

    # ── Defaults ──────────────────────────────────────────────────────────
    @api.model
    def _default_employee_id(self):
        contract_id = self.env.context.get('default_contract_id')
        if not contract_id:
            return False
        contract = self.env['way4tech.manpower.contract'].browse(contract_id)
        return contract.salesperson_id.id or False

    @api.model
    def _default_account_id(self):
        settings = self.env['way4tech.payroll.settings'].get_for_company()
        return settings.commission_expense_account_id.id or False

    # ── Computes ──────────────────────────────────────────────────────────
    @api.depends('date')
    def _compute_bill_month(self):
        for line in self:
            line.bill_month = line.date.strftime('%m/%Y') if line.date else False

    @api.depends('employee_id')
    def _compute_vendor_id(self):
        """CR2 G3 skeptic bug 5 fix: always re-resolve vendor on employee
        change. Prior 'if line.vendor_id: continue' guard silently kept
        the stale vendor when the accountant swapped salespeople.
        readonly=False still lets the user override after this compute."""
        for line in self:
            partner = False
            emp = line.employee_id
            if emp:
                if emp.user_id and emp.user_id.partner_id:
                    partner = emp.user_id.partner_id
                elif hasattr(emp, 'work_contact_id') and emp.work_contact_id:
                    partner = emp.work_contact_id
            line.vendor_id = partner or False

    @api.depends(
        'employee_id', 'date', 'contract_id',
        'contract_id.commission_type',
        'contract_id.pp_actual_profit',
        'contract_id.pp_gross_profit',
        'contract_id.pp_net_profit',
        'contract_id.pp_budgeted_profit',
        'contract_id.invoice_ids',
        'contract_id.invoice_ids.invoice_date',
        'contract_id.invoice_ids.state',
        'contract_id.invoice_ids.move_type',
    )
    def _compute_amount(self):
        """CR2 G3 skeptic bug 3 fix: SKIP billed lines. Once the vendor
        bill has posted, the amount is locked to what's on the GL. If
        the accountant needs to re-quote, they cancel/delete the bill;
        the next recompute will refresh."""
        for line in self:
            if line.state == 'billed':
                continue
            if not line.contract_id or not line.employee_id:
                line.amount = 0.0
                continue
            target = line.date or fields.Date.context_today(line)
            line.amount = line.contract_id._get_commission_amount(
                line.employee_id, target,
            )

    # ── Actions ────────────────────────────────────────────────────────────
    def action_create_bill(self):
        self.ensure_one()
        if self.bill_id:
            raise UserError(_('A vendor bill already exists for this commission line.'))
        # CR3-FINAL Part A: per-item approval, consumed on creation.
        self.contract_id._require_month_approval(record=self)
        if not self.vendor_id:
            raise UserError(_(
                'No vendor could be resolved for salesperson "%s".\n'
                'The employee has no linked User (user_id) and no Work '
                'Contact (work_contact_id). Set one on the HR Employee '
                'record, or pick a vendor manually on this line before '
                'clicking Create Bill.'
            ) % (self.employee_id.name or ''))
        if not self.account_id:
            raise UserError(_(
                'No expense account set. Configure it in Configuration → '
                'Payroll & Accounting Setup → Sales Person Commission '
                'Rules → Commission Expense Account, or set it directly '
                'on this line.'
            ))
        # Skeptic bug 1: template-missing check moved from compute to this
        # user-triggered action. Raise here so the accountant knows why
        # the amount is zero at the moment they try to bill.
        if not self.amount:
            template = self.env['way4tech.commission.template'].search([
                ('employee_id', '=', self.employee_id.id),
                ('company_id', '=', self.company_id.id),
            ], limit=1)
            if not template:
                raise UserError(_(
                    'No commission template configured for salesperson '
                    '"%s". Configure the rate in Configuration → Payroll & '
                    'Accounting Setup → Sales Person Commission Rules.'
                ) % (self.employee_id.name or ''))
            raise UserError(_(
                'Commission amount is zero — nothing to bill. Check the '
                "contract's Commission Type, the employee's commission "
                'template rate, and profitability (percentage modes are '
                'gated: Actual Profit must be positive).'
            ))

        settings = self.env['way4tech.payroll.settings'].get_for_company(self.company_id.id)
        journal = settings.project_expense_journal_id or self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        bill_line_vals = {
            'name': self.description or (_('Sales Person Commission — %s') % (self.employee_id.name or '')),
            'quantity': 1.0,
            'price_unit': self.amount,
            'account_id': self.account_id.id,
        }
        distribution = self.contract_id._resolve_analytic_distribution(settings)
        if distribution:
            bill_line_vals['analytic_distribution'] = distribution

        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.vendor_id.id,
            'invoice_date': self.date,
            'date': self.date,
            'company_id': self.company_id.id,
            'ref': '%s / Commission %s' % (self.contract_id.name, self.employee_id.name or ''),
            'invoice_line_ids': [(0, 0, bill_line_vals)],
        }
        if self.contract_id.invoice_ids:
            bill_vals['payment_reference'] = self.contract_id._compose_reference_string(
                invoice=self.contract_id.invoice_ids[:1],
            )
        if journal:
            bill_vals['journal_id'] = journal.id
        if self.contract_id.way4tech_project_id:
            bill_vals['way4tech_project_id'] = self.contract_id.way4tech_project_id.id
        if self.contract_id.way4tech_category_id:
            bill_vals['way4tech_category_id'] = self.contract_id.way4tech_category_id.id
        all_tags = (self.contract_id.tag_ids | self.tag_ids)
        if all_tags:
            bill_vals['way4tech_tag_ids'] = [(6, 0, all_tags.ids)]

        bill = self.env['account.move'].create(bill_vals)
        self.contract_id._apply_ksa_account_overrides(bill)
        # CR2 G4: pin the specific bill line for per-line sync-back.
        self.write({
            'bill_id': bill.id,
            'bill_line_id': bill.invoice_line_ids[:1].id or False,
            'state': 'billed',
        })
        # CR3-FINAL Part A: burn the approval.
        self.contract_id._consume_approval(self)
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'res_id': bill.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_bill(self):
        self.ensure_one()
        if not self.bill_id:
            raise UserError(_('No vendor bill linked to this commission line.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'res_id': self.bill_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _sync_amount_from_move(self, move):
        """CR2 G4 amendment A: pull price_subtotal from pinned bill line
        back into this commission line. amount is store=True compute
        readonly=False; direct write persists because _compute_amount
        early-returns on state=='billed' (G3 skeptic bug 3 fix)."""
        self.ensure_one()
        if move.move_type not in ('in_invoice', 'in_refund'):
            return
        if not self.bill_line_id:
            return
        new_amount = self.bill_line_id.price_subtotal or 0.0
        if new_amount != self.amount:
            self.with_context(way4tech_skip_move_sync=True).write({'amount': new_amount})

    def unlink(self):
        """CR2 G4 item 4/5: block deletion only when linked vendor bill is
        POSTED (skeptic amendment E — allow delete for draft/cancelled)."""
        for line in self:
            move = line.bill_id
            if move and move.state == 'posted':
                raise UserError(_(
                    'Cannot delete this Sales Person Commission line — the '
                    'linked vendor bill "%s" is POSTED. Reset the bill to '
                    'draft or cancel it from the Accounting menu first, then '
                    'retry.'
                ) % move.display_name)
        return super().unlink()
