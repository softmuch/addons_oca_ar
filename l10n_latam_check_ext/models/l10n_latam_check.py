import logging
from datetime import timedelta
from odoo import models, fields, api, _
from odoo.fields import Domain

_logger = logging.getLogger(__name__)


class L10nLatamCheckExt(models.Model):
    _inherit = 'l10n_latam.check'

    # Checks are now created instantly on pos.payment (see pos_payment.py in
    # this module), well before there's necessarily any account.payment to
    # link to -- that only gets created later, at session close, and only
    # if the order was invoiced. Core's own required=True would block that.
    payment_id = fields.Many2one(required=False)

    # Core declares this `related='payment_id.company_id', store=True` with
    # no `readonly=False` -- a readonly related field, so any value passed
    # explicitly in create()/write() while payment_id is still empty gets
    # silently dropped and recomputed to False from the (empty) relation.
    # `readonly=False` makes it a writable related: an explicit value sticks
    # until payment_id is eventually set, at which point it recomputes from
    # the real payment as usual.
    company_id = fields.Many2one(related='payment_id.company_id', store=True, readonly=False)

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

    # ── Expiring soon ────────────────────────────────────────────────────────

    is_expiring_soon = fields.Boolean(
        string='Por vencer',
        compute='_compute_is_expiring_soon',
        search='_search_is_expiring_soon',
    )

    @api.depends(
        'payment_date', 'payment_method_code', 'company_id',
        'company_id.l10n_latam_own_check_alert_days',
        'company_id.l10n_latam_third_check_alert_days',
    )
    def _compute_is_expiring_soon(self):
        today = fields.Date.today()
        for rec in self:
            if rec.payment_method_code == 'own_checks':
                days = rec.company_id.l10n_latam_own_check_alert_days
            else:
                days = rec.company_id.l10n_latam_third_check_alert_days
            rec.is_expiring_soon = bool(
                days and rec.payment_date
                and today <= rec.payment_date <= today + timedelta(days=days)
            )

    def _search_is_expiring_soon(self, operator, value):
        today = fields.Date.today()
        sub_domains = []
        for company in self.env['res.company'].search([]):
            for codes, days in [
                (['own_checks'], company.l10n_latam_own_check_alert_days),
                (['new_third_party_checks'], company.l10n_latam_third_check_alert_days),
            ]:
                if not days:
                    continue
                sub_domains.append(Domain([
                    ('company_id', '=', company.id),
                    ('payment_method_code', 'in', codes),
                    ('payment_date', '>=', today),
                    ('payment_date', '<=', today + timedelta(days=days)),
                ]))
        combined = Domain.OR(sub_domains) if sub_domains else Domain([('id', '=', False)])
        if operator == 'in':
            want_true = True in value
        elif operator == 'not in':
            want_true = True not in value
        elif operator == '=':
            want_true = bool(value)
        else:  # !=
            want_true = not bool(value)
        return combined if want_true else ~combined

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
