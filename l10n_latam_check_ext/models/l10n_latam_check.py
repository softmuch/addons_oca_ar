from datetime import timedelta
from odoo import models, fields, _


class L10nLatamCheckExt(models.Model):
    _inherit = 'l10n_latam.check'

    check_type = fields.Selection(
        selection=[
            ('common', 'Cheque Común'),
            ('deferred', 'Cheque de Pago Diferido (CPD)'),
        ],
        string='Tipo de Cheque',
        help=(
            "Cheque Común: El más utilizado. Se hace efectivo al momento de presentarlo en el banco "
            "(aunque en la práctica suele usarse con fecha futura, lo que técnicamente es un "
            "\"cheque diferido informal\" o \"cheque de pago a la vista postdatado\"). "
            "Vigencia: 30 días corridos desde la fecha de emisión.\n\n"
            "Cheque de Pago Diferido (CPD): Tiene una fecha de pago futura indicada explícitamente, "
            "que puede ir de 1 hasta 360 días desde la emisión. Es muy usado en Argentina como "
            "instrumento de financiamiento, ya que puede negociarse (descontarse) en el mercado de "
            "capitales antes de su vencimiento, incluso a través del sistema de cheques electrónicos "
            "(eCheq) en mercados como el MAE o Bolsas y Mercados Argentinos (BYMA)."
        ),
    )

    issue_date = fields.Date(
        string='Fecha de Emisión',
        help=(
            "Fecha en que se emitió el cheque. "
            "Para cheques comunes determina el inicio de la vigencia de 30 días corridos. "
            "Para cheques de pago diferido (CPD) es el punto de partida desde el cual se cuenta "
            "el plazo de pago diferido (entre 1 y 360 días)."
        ),
    )

    # ── Cron helpers ─────────────────────────────────────────────────────────

    def _cron_alert_own_checks(self):
        self._cron_alert_checks(
            payment_method_codes=['own_checks'],
            days_field='l10n_latam_own_check_alert_days',
            users_field='l10n_latam_own_check_alert_user_ids',
        )

    def _cron_alert_third_party_checks(self):
        self._cron_alert_checks(
            payment_method_codes=['new_third_party_checks'],
            days_field='l10n_latam_third_check_alert_days',
            users_field='l10n_latam_third_check_alert_user_ids',
        )

    def _cron_alert_checks(self, payment_method_codes, days_field, users_field):
        today = fields.Date.today()
        for company in self.env['res.company'].search([]):
            alert_days = getattr(company, days_field)
            alert_users = getattr(company, users_field)
            if not alert_days or not alert_users:
                continue
            target_date = today + timedelta(days=alert_days)
            checks = self.sudo().search([
                # ('issue_state', '=', 'handed'),
                ('payment_date', '=', target_date),
                ('payment_method_code', 'in', payment_method_codes),
                ('company_id', '=', company.id),
            ])
            for check in checks:
                check.sudo()._send_check_alert(alert_users)

    def _send_check_alert(self, users):
        self.ensure_one()
        body = _(
            'Aviso de vencimiento: el cheque <b>%(name)s</b> vence el <b>%(date)s</b> '
            '(Importe: %(amount)s %(currency)s).',
            name=self.name or '-',
            date=self.payment_date,
            amount=self.amount,
            currency=self.currency_id.name,
        )
        # Chatter message → Odoo inbox notification + email a los partners
        self.message_post(
            body=body,
            partner_ids=users.mapped('partner_id').ids,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',
        )
        # Actividad por usuario → visible en vistas de actividades y calendario
        activity_summary = _('Cheque próximo a vencer: %s', self.name or '-')
        if not self.activity_ids.filtered(lambda a: a.summary == activity_summary):
            for user in users:
                self.activity_schedule(
                    'mail.mail_activity_data_todo',
                    date_deadline=self.payment_date,
                    summary=activity_summary,
                    user_id=user.id,
                )
