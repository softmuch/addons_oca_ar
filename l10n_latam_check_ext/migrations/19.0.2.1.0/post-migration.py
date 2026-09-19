# License OPL-1


def migrate(cr, version):
    """`check_state_third` is now only set for third-party checks and
    `check_state_own` only for own ones (a transferred check has no
    own-check state). The stored copies computed before this rule kept
    values on the wrong kind of check: recompute them in SQL."""
    cr.execute(
        """
        UPDATE l10n_latam_check
           SET check_state_third = CASE WHEN check_kind = 'own' THEN NULL ELSE check_state END,
               check_state_own = CASE
                   WHEN check_kind = 'own' AND check_state <> 'transferred' THEN check_state
                   ELSE NULL END
        """
    )
    # pos.payment.check_state mirrors the check's third-party state
    cr.execute(
        """
        UPDATE pos_payment p
           SET check_state = c.check_state_third
          FROM l10n_latam_check c
         WHERE p.l10n_latam_check_id = c.id
        """
    )
