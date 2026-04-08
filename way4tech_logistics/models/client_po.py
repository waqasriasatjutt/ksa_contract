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
        help="Sum of untaxed amounts from all posted customer invoices linked to this PO.",
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

    # ── Links ─────────────────────────────────────────────────────────────────
    invoice_ids = fields.One2many(
        'account.move', 'way4tech_po_id', string='Invoices',
        domain=[('move_type', '=', 'out_invoice')],
    )
    invoice_count = fields.Integer(
        string='Invoices',
        compute='_compute_balance', store=True,
    )
    trip_ids = fields.One2many(
        'way4tech.truck.trip', 'po_id', string='Trips',
    )
    trip_count = fields.Integer(
        string='Trips',
        compute='_compute_balance', store=True,
    )
    contract_ids = fields.One2many(
        'way4tech.manpower.contract', 'po_id', string='Manpower Contracts',
    )
    contract_count = fields.Integer(
        string='Contracts',
        compute='_compute_counts', store=True,
    )
    rental_ids = fields.One2many(
        'way4tech.equipment.rental', 'po_id', string='Equipment Rentals',
    )
    rental_count = fields.Integer(
        string='Rentals',
        compute='_compute_counts', store=True,
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

    # ── Balance Computation ───────────────────────────────────────────────────

    @api.depends(
        'invoice_ids', 'invoice_ids.state', 'invoice_ids.amount_untaxed',
        'trip_ids', 'trip_ids.state',
        'total_amount',
    )
    def _compute_balance(self):
        for rec in self:
            # Consumed = sum of posted customer invoices linked to this PO
            posted_invoices = rec.invoice_ids.filtered(
                lambda m: m.state == 'posted' and m.move_type == 'out_invoice'
            )
            consumed = sum(posted_invoices.mapped('amount_untaxed'))

            remaining = rec.total_amount - consumed
            pct = (consumed / rec.total_amount * 100) if rec.total_amount else 0.0

            rec.consumed_amount = consumed
            rec.remaining_balance = max(remaining, 0.0)
            rec.utilization_pct = pct
            rec.invoice_count = len(posted_invoices)
            rec.trip_count = len(rec.trip_ids.filtered(
                lambda t: t.state in ('confirmed', 'done')
            ))

            if pct >= 100:
                rec.state = 'closed'
            elif pct >= 80:
                rec.state = 'near_limit'
            else:
                rec.state = 'open'

    @api.depends('contract_ids', 'rental_ids')
    def _compute_counts(self):
        for rec in self:
            rec.contract_count = len(rec.contract_ids)
            rec.rental_count = len(rec.rental_ids)

    # ── Notifications ─────────────────────────────────────────────────────────

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
        group = self.env.ref('way4tech_logistics.group_logistics_manager', raise_if_not_found=False)
        partner_ids = group.users.mapped('partner_id').ids if group else []
        self.message_post(
            body=_(
                '<b>PO Near Limit Alert</b><br/>'
                'PO <b>%(name)s</b> for client <b>%(client)s</b> has reached '
                '<b>%(pct).1f%%</b> utilization (%(consumed)s / %(total)s SAR).<br/>'
                'Remaining balance: <b>%(remaining)s SAR</b>.'
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
        self.message_post(
            body=_(
                '<b>PO Closed — 100%% Consumed</b><br/>'
                'PO <b>%(name)s</b> for client <b>%(client)s</b> has been fully consumed '
                '(%(consumed)s / %(total)s SAR).'
            ) % {
                'name': self.name,
                'client': self.client_id.name or '',
                'consumed': '%.2f' % self.consumed_amount,
                'total': '%.2f' % self.total_amount,
            },
            subtype_xmlid='mail.mt_note',
        )

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_view_invoices(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoices — %s') % self.name,
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('way4tech_po_id', '=', self.id), ('move_type', '=', 'out_invoice')],
        }

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

    def action_view_contracts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Manpower Contracts — %s') % self.name,
            'res_model': 'way4tech.manpower.contract',
            'view_mode': 'list,form',
            'domain': [('po_id', '=', self.id)],
            'context': {
                'default_po_id': self.id,
                'default_client_id': self.client_id.id,
            },
        }

    def action_view_rentals(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Equipment Rentals — %s') % self.name,
            'res_model': 'way4tech.equipment.rental',
            'view_mode': 'list,form',
            'domain': [('po_id', '=', self.id)],
            'context': {
                'default_po_id': self.id,
                'default_client_id': self.client_id.id,
            },
        }

    def action_renew_po(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('New PO (Renewal)'),
            'res_model': 'way4tech.client.po',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_client_id': self.client_id.id,
                'default_description': _('Renewal of %s') % self.name,
            },
        }
