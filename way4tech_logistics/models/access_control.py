import datetime
from odoo import api, fields, models, _
from odoo.exceptions import UserError

# How many days back a Logistics User (non-manager) is allowed to date a journal entry.
BACKDATE_LIMIT_DAYS = 7


class AccountMove(models.Model):
    """
    Access control for journal entries:
    - Logistics Users cannot post entries dated more than BACKDATE_LIMIT_DAYS in the past.
    - Logistics Users cannot delete posted transactions.
    - Logistics Managers have no restriction.
    """
    _inherit = 'account.move'

    @api.constrains('date', 'state')
    def _check_backdate_restriction(self):
        for rec in self:
            # Only enforce for way4tech logistics users (not managers, not admins)
            if not rec.env.user.has_group('way4tech_logistics.group_logistics_user'):
                continue
            if rec.env.user.has_group('way4tech_logistics.group_logistics_manager'):
                continue
            if not rec.date:
                continue
            cutoff = datetime.date.today() - datetime.timedelta(days=BACKDATE_LIMIT_DAYS)
            if rec.date < cutoff:
                raise UserError(_(
                    'Back-dated entries are restricted.\n\n'
                    'You cannot create or edit journal entries dated more than '
                    '%d days in the past (entry date: %s, earliest allowed: %s).\n\n'
                    'Please ask your Logistics Manager to post this entry.'
                ) % (BACKDATE_LIMIT_DAYS, rec.date, cutoff))

    def unlink(self):
        """Restrict deleting posted/locked transactions for non-managers."""
        if (self.env.user.has_group('way4tech_logistics.group_logistics_user')
                and not self.env.user.has_group('way4tech_logistics.group_logistics_manager')):
            posted = self.filtered(lambda m: m.state == 'posted')
            if posted:
                raise UserError(_(
                    'Deleting posted transactions is restricted.\n\n'
                    'You cannot delete entries that have already been posted.\n'
                    'Contact your Logistics Manager.'
                ))
        return super().unlink()


class ResPartner(models.Model):
    """
    Access control for vendor/supplier creation:
    - Logistics Users cannot create or promote a partner to a supplier (supplier_rank > 0).
    - Logistics Managers have full access.
    """
    _inherit = 'res.partner'

    @api.model_create_multi
    def create(self, vals_list):
        if (self.env.user.has_group('way4tech_logistics.group_logistics_user')
                and not self.env.user.has_group('way4tech_logistics.group_logistics_manager')):
            for vals in vals_list:
                if vals.get('supplier_rank', 0) > 0:
                    raise UserError(_(
                        'Only Logistics Managers can register new vendors/suppliers.\n'
                        'Contact your manager to add this supplier.'
                    ))
        return super().create(vals_list)

    def write(self, vals):
        if (self.env.user.has_group('way4tech_logistics.group_logistics_user')
                and not self.env.user.has_group('way4tech_logistics.group_logistics_manager')):
            if vals.get('supplier_rank', 0) > 0:
                raise UserError(_(
                    'Only Logistics Managers can create or modify vendor records.\n'
                    'Contact your manager.'
                ))
        return super().write(vals)


class AccountAccount(models.Model):
    """
    Access control for chart of accounts:
    - Logistics Users cannot create new accounts (ledger creation restriction).
    - Logistics Managers have full access.
    """
    _inherit = 'account.account'

    @api.model_create_multi
    def create(self, vals_list):
        if (self.env.user.has_group('way4tech_logistics.group_logistics_user')
                and not self.env.user.has_group('way4tech_logistics.group_logistics_manager')):
            raise UserError(_(
                'Only Logistics Managers can create new accounts in the chart of accounts.\n'
                'Contact your manager.'
            ))
        return super().create(vals_list)

    def write(self, vals):
        if (self.env.user.has_group('way4tech_logistics.group_logistics_user')
                and not self.env.user.has_group('way4tech_logistics.group_logistics_manager')):
            raise UserError(_(
                'Only Logistics Managers can modify chart of accounts entries.\n'
                'Contact your manager.'
            ))
        return super().write(vals)
