from odoo import fields, models, _
from odoo.exceptions import UserError


class Way4TechRejectionWizard(models.TransientModel):
    """
    Wizard opened when a manager rejects a pending journal entry.
    Records the rejection reason, returns entry to Draft and notifies the submitter.
    """
    _name = 'way4tech.rejection.wizard'
    _description = 'Journal Entry Rejection Wizard'

    move_ids = fields.Many2many('account.move', string='Entries')
    reason = fields.Text(
        string='Rejection Reason', required=True,
        help='Provide a clear reason. It will be visible to the accountant in the chatter.',
    )

    def action_reject(self):
        if not self.env.user.has_group('way4tech_logistics.group_logistics_manager'):
            raise UserError(_('Only Logistics Managers can reject journal entries.'))
        if not self.move_ids:
            raise UserError(_('No entries selected.'))
        for move in self.move_ids:
            move.write({
                'way4tech_approval_state': 'rejected',
                'way4tech_rejection_reason': self.reason,
            })
            # Return to draft if posted
            if move.state == 'posted':
                move.button_draft()
            move.message_post(
                body=_(
                    'Entry <strong>rejected</strong> by %s.<br/>'
                    '<strong>Reason:</strong> %s'
                ) % (self.env.user.name, self.reason)
            )
        return {'type': 'ir.actions.act_window_close'}
