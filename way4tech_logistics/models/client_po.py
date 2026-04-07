from odoo import api, fields, models, _
from odoo.exceptions import UserError


class Way4TechClientPO(models.Model):
    _name = 'way4tech.client.po'
    _description = 'Client PO Balance Tracker'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'po_date desc, name desc'

    name = fields.Char(string='PO Reference', required=True, tracking=True)
    client_id = fields.Many2one(
        'res.partner', string='Client', required=True, tracking=True,
    )
    po_date = fields.Date(
        string='PO Date', required=True, default=fields.Date.today,
    )
    expiry_date = fields.Date(string='Expiry Date')
    description = fields.Char(string='Scope / Description')

    total_amount = fields.Monetary(
        string='PO Total Amount', required=True,
        currency_field='currency_id', tracking=True,
    )
    consumed_amount = fields.Monetary(
        string='Consumed Amount',
        compute='_compute_balance', store=True,
        currency_field='currency_id',
        help="Sum of revenue on all confirmed/done trips linked to this PO.",
    )
    remaining_balance = fields.Monetary(
        string='Remaining Balance',
        compute='_compute_balance', store=True,
        currency_field='currency_id',
    )
    utilization_pct = fields.Float(
        string='Utilization %',
        compute='_compute_balance', store=True,
        digits=(5, 1),
    )
    state = fields.Selection(
        selection=[
            ('open', 'Open'),
            ('near_limit', 'Near Limit (80%+)'),
            ('closed', 'Closed'),
        ],
        string='Status', default='open', tracking=True,
        compute='_compute_balance', store=True,
    )
    trip_ids = fields.One2many(
        'way4tech.truck.trip', 'po_id', string='Trips',
    )
    trip_count = fields.Integer(
        string='Trips',
        compute='_compute_balance', store=True,
    )
    company_id = fields.Many2one(
        'res.company', string='Company',
        default=lambda self: self.env.company, required=True,
    )
    currency_id = fields.Many2one(
        'res.currency', related='company_id.currency_id',
        readonly=True, store=True,
    )
    notes = fields.Text(string='Internal Notes')

    @api.depends('trip_ids.revenue', 'trip_ids.state', 'total_amount')
    def _compute_balance(self):
        for rec in self:
            active = rec.trip_ids.filtered(lambda t: t.state in ('confirmed', 'done'))
            consumed = sum(active.mapped('revenue'))
            remaining = rec.total_amount - consumed
            pct = (consumed / rec.total_amount * 100) if rec.total_amount else 0.0
            rec.consumed_amount = consumed
            rec.remaining_balance = max(remaining, 0.0)
            rec.utilization_pct = pct
            rec.trip_count = len(active)
            if pct >= 100:
                rec.state = 'closed'
            elif pct >= 80:
                rec.state = 'near_limit'
            else:
                rec.state = 'open'

    def write(self, vals):
        old_states = {rec.id: rec.state for rec in self}
        result = super().write(vals)
        for rec in self:
            old = old_states.get(rec.id, 'open')
            if old != 'near_limit' and rec.state == 'near_limit':
                rec._notify_near_limit()
            elif old != 'closed' and rec.state == 'closed':
                rec._notify_closed()
        return result

    def _notify_near_limit(self):
        """Post chatter message + notify logistics managers when PO reaches 80%."""
        group = self.env.ref('way4tech_logistics.group_logistics_manager', raise_if_not_found=False)
        partner_ids = group.users.mapped('partner_id').ids if group else []
        self.message_post(
            body=_(
                '<b>PO Near Limit Alert</b><br/>'
                'PO <b>%(name)s</b> for client <b>%(client)s</b> has reached '
                '<b>%(pct).1f%%</b> utilization (%(consumed)s / %(total)s SAR).<br/>'
                'Remaining balance: <b>%(remaining)s SAR</b>. '
                'Please review before confirming further trips.'
            ) % {
                'name': self.name,
                'client': self.client_id.name or '',
                'pct': self.utilization_pct,
                'consumed': '%.2f' % self.consumed_amount,
                'total': '%.2f' % self.total_amount,
                'remaining': '%.2f' % self.remaining_balance,
            },
            subtype_xmlid='mail.mt_note',
            partner_ids=partner_ids,
        )

    def _notify_closed(self):
        """Post chatter message when PO reaches 100% and auto-closes."""
        self.message_post(
            body=_(
                '<b>PO Closed — 100%% Consumed</b><br/>'
                'PO <b>%(name)s</b> for client <b>%(client)s</b> has been fully consumed '
                '(%(consumed)s / %(total)s SAR). No further trips can be linked to this PO.'
            ) % {
                'name': self.name,
                'client': self.client_id.name or '',
                'consumed': '%.2f' % self.consumed_amount,
                'total': '%.2f' % self.total_amount,
            },
            subtype_xmlid='mail.mt_note',
        )

    def action_view_trips(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Trips — %s') % self.name,
            'res_model': 'way4tech.truck.trip',
            'view_mode': 'list,form',
            'domain': [('po_id', '=', self.id)],
            'context': {
                'default_po_id': self.id,
                'default_client_id': self.client_id.id,
            },
        }

    def action_renew_po(self):
        """Open a blank new PO pre-filled with the same client for renewal."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('New PO (Renewal)'),
            'res_model': 'way4tech.client.po',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_client_id': self.client_id.id,
                'default_company_id': self.company_id.id,
                'default_description': _('Renewal of %s') % self.name,
            },
        }
