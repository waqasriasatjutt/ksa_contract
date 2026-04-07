from odoo import api, fields, models, _
from odoo.exceptions import UserError


class SetupWizardLine(models.TransientModel):
    _name = 'way4tech.setup.wizard.line'
    _description = 'Setup Wizard Preview Line'
    _order = 'item_type, name'

    wizard_id = fields.Many2one(
        'way4tech.setup.wizard',
        string='Wizard',
        ondelete='cascade',
        required=True,
    )
    item_type = fields.Selection([
        ('analytic_default', 'Analytic Account — Company Default'),
        ('analytic_truck', 'Analytic Account — Truck'),
        ('analytic_client', 'Analytic Account — Client/Platform'),
    ], string='Type', required=True)
    name = fields.Char(string='Name to Create', required=True)
    selected = fields.Boolean(string='Create', default=True)
    status = fields.Selection([
        ('pending', 'Will Create'),
        ('exists', 'Already Exists — Will Skip'),
        ('created', 'Created'),
    ], default='pending', string='Status')


class SetupWizard(models.TransientModel):
    _name = 'way4tech.setup.wizard'
    _description = 'Way4Tech Initial Setup Wizard'

    # ── Step tracker ──────────────────────────────────────────────────────────
    state = fields.Selection([
        ('options', 'Step 1: Choose Options'),
        ('preview', 'Step 2: Review & Create'),
        ('done', 'Step 3: Done'),
    ], default='options', string='Step')

    # ── What to create ────────────────────────────────────────────────────────
    create_default_analytic = fields.Boolean(
        string='Create Company Default Analytic Account',
        default=True,
        help='Creates a single analytic account and sets it as the company default '
             'in Payroll & Accounting Setup. Any document with no specific analytic '
             'will fall back to this one.',
    )
    default_analytic_name = fields.Char(
        string='Name for Default Account',
        default='General Operations',
    )
    create_truck_analytics = fields.Boolean(
        string='Create One Analytic Account per Truck',
        default=True,
        help='Creates one analytic account for every truck currently in the system. '
             'Each truck\'s analytic account is assigned to that truck automatically. '
             'All trips, maintenance costs and investor payables for that truck will '
             'then be tagged — giving you a per-truck P&L in Analytic Reports.',
    )
    create_client_analytics = fields.Boolean(
        string='Create One Analytic Account per Client/Platform',
        default=False,
        help='Creates one analytic account for every company-type customer partner. '
             'Useful if you want to track commission income or manpower revenue '
             'broken down by client in the Analytic Report.',
    )
    analytic_plan_id = fields.Many2one(
        'account.analytic.plan',
        string='Analytic Plan',
        help='All new analytic accounts will be placed under this plan. '
             'Leave blank to use the first existing plan, or one called "Operations" '
             'will be created automatically.',
    )

    # ── Preview lines ─────────────────────────────────────────────────────────
    line_ids = fields.One2many(
        'way4tech.setup.wizard.line', 'wizard_id',
        string='Items to Create',
    )

    # ── Result summary ────────────────────────────────────────────────────────
    created_count = fields.Integer(string='Accounts Created', default=0, readonly=True)
    skipped_count = fields.Integer(string='Already Existed (Skipped)', default=0, readonly=True)
    assigned_truck_count = fields.Integer(string='Trucks Assigned', default=0, readonly=True)
    default_assigned = fields.Boolean(
        string='Company Default Updated',
        default=False,
        readonly=True,
    )

    # ── Computed helper ───────────────────────────────────────────────────────
    pending_count = fields.Integer(
        compute='_compute_pending_count',
        string='Items Will Be Created',
    )

    @api.depends('line_ids.status', 'line_ids.selected')
    def _compute_pending_count(self):
        for rec in self:
            rec.pending_count = len(
                rec.line_ids.filtered(lambda l: l.selected and l.status == 'pending')
            )

    # ── Step 1 → Step 2 ──────────────────────────────────────────────────────
    def action_preview(self):
        self.ensure_one()
        # Remove any previous preview lines
        self.line_ids.unlink()

        plan = self._get_or_create_plan()
        plan_name = plan.name if plan else ''
        company = self.env.company
        lines_to_create = []

        # --- Default analytic account ---
        if self.create_default_analytic:
            name = (self.default_analytic_name or 'General Operations').strip()
            if not name:
                name = 'General Operations'
            already = self.env['account.analytic.account'].search([
                ('name', '=', name),
                ('company_id', 'in', [company.id, False]),
            ], limit=1)
            lines_to_create.append({
                'item_type': 'analytic_default',
                'name': name,
                'selected': True,
                'status': 'exists' if already else 'pending',
            })

        # --- One analytic per truck ---
        if self.create_truck_analytics:
            trucks = self.env['fleet.vehicle'].search([
                ('company_id', '=', company.id),
            ])
            if not trucks:
                trucks = self.env['fleet.vehicle'].search([])
            for truck in trucks:
                already = self.env['account.analytic.account'].search([
                    ('name', '=', truck.name),
                    ('company_id', 'in', [company.id, False]),
                ], limit=1)
                lines_to_create.append({
                    'item_type': 'analytic_truck',
                    'name': truck.name,
                    'selected': True,
                    'status': 'exists' if already else 'pending',
                })

        # --- One analytic per client ---
        if self.create_client_analytics:
            clients = self.env['res.partner'].search([
                ('customer_rank', '>', 0),
                ('is_company', '=', True),
            ], limit=50, order='name asc')
            for client in clients:
                already = self.env['account.analytic.account'].search([
                    ('name', '=', client.name),
                    ('company_id', 'in', [company.id, False]),
                ], limit=1)
                lines_to_create.append({
                    'item_type': 'analytic_client',
                    'name': client.name,
                    'selected': True,
                    'status': 'exists' if already else 'pending',
                })

        if not lines_to_create:
            raise UserError(_(
                'Nothing to preview. Please enable at least one option above, '
                'and make sure you have trucks or clients in the system.'
            ))

        # Bulk-create lines
        for vals in lines_to_create:
            vals['wizard_id'] = self.id
        self.env['way4tech.setup.wizard.line'].create(lines_to_create)

        self.state = 'preview'
        return self._reopen()

    # ── Step 2 → Step 3 ──────────────────────────────────────────────────────
    def action_create_selected(self):
        self.ensure_one()
        plan = self._get_or_create_plan()
        company = self.env.company
        settings = self.env['way4tech.payroll.settings'].get_for_company(company.id)

        created = 0
        skipped = 0
        assigned_trucks = 0
        default_done = False

        for line in self.line_ids.filtered(lambda l: l.selected):
            if line.status == 'exists':
                skipped += 1
                continue

            # Create the analytic account
            analytic = self.env['account.analytic.account'].create({
                'name': line.name,
                'plan_id': plan.id if plan else False,
                'company_id': company.id,
            })
            line.status = 'created'
            created += 1

            # Post-creation: auto-assign
            if line.item_type == 'analytic_default':
                if settings and not settings.default_analytic_account_id:
                    settings.default_analytic_account_id = analytic.id
                    default_done = True

            elif line.item_type == 'analytic_truck':
                truck = self.env['fleet.vehicle'].search([
                    ('name', '=', line.name),
                ], limit=1)
                if truck and not truck.analytic_account_id:
                    truck.analytic_account_id = analytic.id
                    assigned_trucks += 1

        self.created_count = created
        self.skipped_count = skipped
        self.assigned_truck_count = assigned_trucks
        self.default_assigned = default_done
        self.state = 'done'
        return self._reopen()

    # ── Back button ───────────────────────────────────────────────────────────
    def action_back_to_options(self):
        self.ensure_one()
        self.line_ids.unlink()
        self.state = 'options'
        return self._reopen()

    # ── Internal helpers ─────────────────────────────────────────────────────
    def _get_or_create_plan(self):
        if self.analytic_plan_id:
            return self.analytic_plan_id
        plan = self.env['account.analytic.plan'].search([], limit=1)
        if not plan:
            plan = self.env['account.analytic.plan'].create({
                'name': 'Operations',
                'default_applicability': 'optional',
            })
        return plan

    def _reopen(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
