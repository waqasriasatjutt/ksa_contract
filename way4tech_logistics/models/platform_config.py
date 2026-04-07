from odoo import fields, models


class Way4TechPlatformConfig(models.Model):
    _name = 'way4tech.platform.config'
    _description = 'Platform Salary Configuration (Hungerstation, Keeta, etc.)'
    _order = 'name'

    name = fields.Char(
        string='Platform Name',
        required=True,
        help='e.g. Hungerstation, Keeta, The Chefz',
    )
    # ── Minimum working days ──────────────────────────────────────────────────
    min_days = fields.Integer(
        string='Min Days / Month',
        default=27,
        help='Rider must complete this many days to qualify for the fixed salary.',
    )

    # ── Salary amounts ────────────────────────────────────────────────────────
    fixed_salary = fields.Float(
        string='Fixed Salary (≥ min days)',
        digits=(10, 2),
        help='Fixed monthly salary when rider meets the minimum days requirement.',
    )
    per_order_rate = fields.Float(
        string='Per-Order Rate (< min days)',
        digits=(10, 2),
        help='Rate per order when rider did NOT meet the minimum days. '
             'Basic = orders × this rate.',
    )

    # ── Order target & adjustments ────────────────────────────────────────────
    min_orders = fields.Integer(
        string='Min Orders Target / Month',
        default=450,
    )
    short_order_rate = fields.Float(
        string='Deduction per Short Order (SAR)',
        digits=(10, 2),
        help='SAR deducted for each order below the minimum target.',
    )
    excess_order_rate = fields.Float(
        string='Bonus per Extra Order (SAR)',
        digits=(10, 2),
        help='SAR added for each order above the minimum target.',
    )

    company_id = fields.Many2one(
        comodel_name='res.company',
        string='Company',
        default=lambda self: self.env.company,
    )
    active = fields.Boolean(default=True)
    notes = fields.Text(string='Notes')

    # ── Helper ────────────────────────────────────────────────────────────────
    def compute_salary(self, valid_days, orders_completed):
        """Return (basic_salary, order_adjustment) for the given rider data.
        valid_days: int
        orders_completed: int
        Returns (basic, adjustment) — adjustment is positive=bonus, negative=deduction
        """
        self.ensure_one()
        days = valid_days or 0
        orders = orders_completed or 0

        if days >= self.min_days:
            basic = self.fixed_salary
            diff = orders - self.min_orders
            if diff < 0:
                adjustment = diff * self.short_order_rate   # negative (deduction)
            elif diff > 0:
                adjustment = diff * self.excess_order_rate  # positive (bonus)
            else:
                adjustment = 0.0
        else:
            # Per-order rate tier — no order adjustment
            basic = orders * self.per_order_rate
            adjustment = 0.0

        return basic, adjustment
