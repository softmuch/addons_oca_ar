# License OPL-1


def migrate(cr, version):
    """`check_state` went from {not_collected, collected, not_paid, paid} to
    {not_paid, paid, transferred}. Done in SQL BEFORE the registry reloads
    `ir_model_fields_selection` so no row is ever left holding a value
    outside the new Selection (and because `pos.payment.write` deliberately
    refuses `check_state`). 'transferred' is set later, by
    `odossey_purchase_pos_payment_check`'s own migration, from
    `handed_to_partner_id`."""
    for table in ("l10n_latam_check", "pos_payment"):
        cr.execute(f"UPDATE {table} SET check_state = 'not_paid' WHERE check_state = 'not_collected'")
        cr.execute(f"UPDATE {table} SET check_state = 'paid' WHERE check_state = 'collected'")
