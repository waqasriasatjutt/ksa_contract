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
import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError

# Words that say nothing about which company this is, so they are skipped when
# a document code is suggested from the company name.
_GENERIC_WORDS = {
    'al', 'the', 'and', 'est', 'llc', 'wll', 'ltd', 'co', 'company', 'sons',
    'establishment', 'contracting', 'contracts', 'trading', 'traders',
    'services', 'service', 'logistic', 'logistics', 'facility', 'general',
    'international', 'group', 'enterprises', 'enterprise', 'holding',
}


class ResCompanyDocPrefix(models.Model):
    """Document references carry the company's own short code.

    Every number series in this module used to start with "WAY4TECH", our name
    inside the client's paperwork, and one shared counter meant two companies
    could reach the same number. Each company now has its own code and its own
    counter, and the code is theirs to change.
    """
    _inherit = 'res.company'

    way4tech_doc_prefix = fields.Char(
        string='Document Code',
        help='Short code at the front of the references this system generates, '
             'for example AZT/TRIP/2026/0001. Suggested from the company name '
             'when the company is created; change it to whatever this company '
             'uses and the next record created follows.',
    )

    @api.model_create_multi
    def create(self, vals_list):
        """A company created from now on gets its own document code, so its
        records never fall back onto a shared one."""
        companies = super().create(vals_list)
        for company in companies:
            if not company.way4tech_doc_prefix:
                company.way4tech_doc_prefix = company._way4tech_suggest_doc_prefix()
        return companies

    def _way4tech_suggest_doc_prefix(self):
        """A short code from the company name: the initials of its meaningful
        words, or the word itself when the name holds only one. A code another
        company already uses gets a number after it, so two companies cannot
        mint the same reference."""
        self.ensure_one()
        words = [w for w in re.split(r'[^A-Za-z0-9]+', self.name or '') if w]
        meaningful = [w for w in words if w.lower() not in _GENERIC_WORDS] or words
        if not meaningful:
            code = 'DOC'
        elif len(meaningful) == 1:
            code = meaningful[0][:6].upper()
        else:
            code = ''.join(word[0] for word in meaningful[:3]).upper()
        taken = set(self.sudo().with_context(active_test=False).search(
            [('id', '!=', self.id)]).mapped('way4tech_doc_prefix'))
        candidate, suffix = code, 1
        while candidate in taken:
            suffix += 1
            candidate = '%s%s' % (code, suffix)
        return candidate

    def _way4tech_doc_sequence(self, base_code, label, token):
        """The number series for one company and one kind of record, created on
        first use.

        Keyed by code and left unpinned, like the other sequences here, so it is
        found whatever company is active. A code the client edits is picked up
        on the next record created.
        """
        self.ensure_one()
        # sudo: a record may be created for a company the user cannot read, and
        # it still needs a reference.
        company = self.sudo()
        code = '%s.company.%s' % (base_code, self.id)
        prefix = '%s/%s/%%(year)s/' % (
            company.way4tech_doc_prefix or company._way4tech_suggest_doc_prefix(), token)
        Sequence = self.env['ir.sequence'].sudo()
        sequence = Sequence.search([('code', '=', code)], limit=1)
        if not sequence:
            sequence = Sequence.create({
                'name': '%s - %s' % (label, company.name or self.id),
                'code': code,
                'prefix': prefix,
                'padding': 4,
                'number_increment': 1,
                'number_next': 1,
                'company_id': False,
            })
        elif sequence.prefix != prefix:
            sequence.prefix = prefix
        return sequence


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
        for fallback in fallbacks:
            if not fallback:
                continue
            if isinstance(fallback, dict):      # a distribution, e.g. from settings
                return fallback
            return {str(fallback.id): 100}      # a single analytic account
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
