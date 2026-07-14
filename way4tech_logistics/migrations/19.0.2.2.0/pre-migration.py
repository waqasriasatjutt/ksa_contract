# -*- coding: utf-8 -*-
"""Pre-migration: map ``salesperson_id`` from ``res.users`` → ``hr.employee``.

In 19.0.2.2.0 we switched ``way4tech.manpower.contract.salesperson_id`` from a
Many2one to ``res.users`` to a Many2one to ``hr.employee`` (client request).
The DB column type is unchanged (integer FK) but the target table flips.
Existing integer IDs on the column reference ``res.users`` rows — they will
NOT match ``hr.employee.id`` values, so Odoo's FK-creation step at end of
module load errors out with ``ForeignKeyViolation`` and the whole upgrade
rolls back.

This pre-migration runs BEFORE Odoo alters the FK — for every contract row
we translate the user_id to the corresponding hr.employee (via
``hr.employee.user_id``); rows with no matching employee are cleared to
NULL so the FK check passes cleanly. Operators can re-select the correct
employee salesperson in the form after upgrade.
"""


def migrate(cr, version):
    if not version:
        return

    # Map user_id -> employee_id (first matching employee per user)
    cr.execute(
        """
        SELECT DISTINCT ON (user_id) user_id, id AS employee_id
        FROM hr_employee
        WHERE user_id IS NOT NULL
        ORDER BY user_id, id
        """
    )
    user_to_employee = dict(cr.fetchall())

    # Fetch every contract's current (user-based) salesperson_id
    cr.execute(
        "SELECT id, salesperson_id FROM way4tech_manpower_contract "
        "WHERE salesperson_id IS NOT NULL"
    )
    rows = cr.fetchall()
    if not rows:
        return

    remapped = cleared = 0
    for contract_id, old_user_id in rows:
        new_emp_id = user_to_employee.get(old_user_id)
        if new_emp_id:
            cr.execute(
                "UPDATE way4tech_manpower_contract "
                "SET salesperson_id = %s WHERE id = %s",
                (new_emp_id, contract_id),
            )
            remapped += 1
        else:
            cr.execute(
                "UPDATE way4tech_manpower_contract "
                "SET salesperson_id = NULL WHERE id = %s",
                (contract_id,),
            )
            cleared += 1

    # Log via psycopg's connection notice (visible in odoo.log)
    cr.execute(
        "SELECT set_config('client_min_messages','notice',false), "
        "1"  # dummy; RAISE NOTICE would need PL/pgSQL
    )
    # No logger available here — trust upgrade log for outcome
