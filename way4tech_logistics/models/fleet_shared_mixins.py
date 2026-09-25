# -*- coding: utf-8 -*-
"""Shared helpers for the Fleet and Commissioning records (2026-09-25).

Two things the client asked for across several screens at once:

* Analytic Distribution instead of a single Analytic Account, so a trip,
  maintenance log or rental can be split over several analytic accounts the
  way Manpower Contracts and Commissioning Business already can. The single
  account each model used before is kept as a fallback so nothing that was
  posted with it changes meaning.
* Partner Statement buttons, which open Odoo's own Partner Ledger filtered to
  one partner, exactly as the Manpower Contract button already does.
"""
from odoo import _, models
from odoo.exceptions import UserError


class Way4TechAnalyticMixin(models.AbstractModel):
    _name = 'way4tech.analytic.mixin'
    _inherit = ['analytic.mixin']
    _description = 'Way4Tech analytic distribution helper'

    def _way4tech_analytic_dist(self, *fallbacks):
        """The distribution to put on generated accounting lines.

        The record's own Analytic Distribution wins. When it is empty the
        single analytic accounts passed as fallbacks are used in order (the
        record's old field, then the vehicle's, then the company default), so
        a record configured before this change keeps posting as it did.
        """
        self.ensure_one()
        if self.analytic_distribution:
            return self.analytic_distribution
        for account in fallbacks:
            if account:
                return {str(account.id): 100}
        return False


class Way4TechPartnerStatementMixin(models.AbstractModel):
    _name = 'way4tech.partner.statement.mixin'
    _description = 'Open the Partner Ledger for a partner on this record'

    def _way4tech_open_partner_ledger(self, partner, label):
        """Odoo's native Partner Ledger, filtered to `partner`.

        Not a custom report: it is the standard Accounting statement with its
        own PDF and XLSX exports, opened the same way the Manpower Contract
        button opens it. Falls back to a partner-scoped journal-items list if
        account_reports is not installed.
        """
        self.ensure_one()
        if not partner:
            raise UserError(_('There is no %s on this record yet.') % label)
        partners = partner | partner.commercial_partner_id
        try:
            action = self.env['ir.actions.actions']._for_xml_id(
                'account_reports.action_account_report_partner_ledger')
        except ValueError:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Partner Statement - %s') % partner.display_name,
                'res_model': 'account.move.line',
                'view_mode': 'list,form',
                'domain': [('partner_id', 'in', partners.ids),
                           ('account_id.account_type', 'in',
                            ('asset_receivable', 'liability_payable'))],
                'context': {'search_default_group_by_account': 1},
            }
        action['params'] = {
            'options': {
                'partner_ids': partners.ids,
                'unfold_all': True,
            },
            'ignore_session': True,
        }
        action['display_name'] = _('Partner Statement - %s') % partner.display_name
        return action
