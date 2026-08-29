import logging
from datetime import timedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
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

    # Same reasoning, but core's own `partner_id` isn't even `store=True` --
    # a non-stored related field has nothing to persist a value into at all
    # while payment_id is empty, so it must be redeclared with both
    # store=True and readonly=False to hold an explicit value (set from the
    # pos.order's own partner in `pos_payment.py`) until payment_id is
    # eventually set.
    partner_id = fields.Many2one(related='payment_id.partner_id', store=True, readonly=False)

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

    # ── Check state (cobrado/pagado) ────────────────────────────────────────
    # One field, four values covering both check kinds: 'not_collected'/
    # 'collected' for a check *received* from a customer (payment_method_code
    # 'new_third_party_checks', or still empty -- pos.payment always creates
    # this kind, instantly, before any payment_method_code exists yet), and
    # 'not_paid'/'paid' for a check the company itself *issues*
    # ('own_checks'). A single Selection can't vary its label set per record,
    # so all four live on the same field; `_check_state_matches_check_kind`
    # below enforces a record only ever uses the pair that matches its kind.
    #
    # This is the only place check_state can be changed -- one check can now
    # settle several pos.order/pos.payment at once (pay.freely.wizard, in
    # odoxeus_rioseed), so it can't live as an independently-writable field
    # on pos.payment anymore. pos.payment.check_state mirrors this as a
    # plain readonly `related`, which Odoo keeps in sync automatically.
    check_state = fields.Selection(
        selection=[
            ('not_collected', 'No Cobrado'),
            ('collected', 'Cobrado'),
            ('not_paid', 'No Pagado'),
            ('paid', 'Pagado'),
        ],
        string='Estado de Cobro/Pago',
        default='not_collected',
        copy=False,
    )

    @api.constrains('check_state')
    def _check_state_matches_check_kind(self):
        for rec in self:
            if not rec.check_state:
                continue
            is_own = rec.payment_method_code == 'own_checks'
            valid = ('not_paid', 'paid') if is_own else ('not_collected', 'collected')
            if rec.check_state not in valid:
                raise ValidationError(_(
                    "El estado '%(state)s' no corresponde a un cheque %(kind)s.",
                    state=dict(rec._fields['check_state'].selection)[rec.check_state],
                    kind='propio' if is_own else 'de cliente',
                ))

    def action_toggle_check_state(self):
        """Flip between the two states of whichever pair applies to this
        check's own kind (own vs third-party) -- the form keeps this behind
        a button rather than a raw editable field since l10n_latam.check's
        form is otherwise `edit="false"` by design (legal/audit document,
        not meant to be freely edited)."""
        for rec in self:
            is_own = rec.payment_method_code == 'own_checks'
            if is_own:
                rec.check_state = 'not_paid' if rec.check_state == 'paid' else 'paid'
            else:
                rec.check_state = 'not_collected' if rec.check_state == 'collected' else 'collected'

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
