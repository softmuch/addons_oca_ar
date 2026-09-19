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
            ('echeq', 'ECHEQ o Cheque Electrónico'),
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
            "(eCheq) en mercados como el MAE o Bolsas y Mercados Argentinos (BYMA).\n\n"
            "ECHEQ o Cheque Electrónico: Se emite, endosa y cobra íntegramente de forma digital a "
            "través de la home banking de cada banco (sistema regulado por el BCRA), sin soporte "
            "en papel. Puede ser común o de pago diferido."
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

    # ── Check kind (own vs third-party) ─────────────────────────────────────
    # `payment_method_code` (core) is a non-stored related off `payment_id`,
    # so it's empty for every check created instantly by pos.payment/the
    # purchase wizards (no account.payment yet) and can't be used in a
    # domain to tell "own" from "third-party" apart. Stored instead, with an
    # explicit default: a check with no payment_id is a third-party one
    # unless whoever creates it says otherwise (`odossey_purchase_pos_
    # payment_check`'s "new check" flow creates own checks this way).
    check_kind = fields.Selection(
        selection=[('third_party', 'De Terceros'), ('own', 'Propio')],
        string='Tipo de Cheque (propio/terceros)',
        compute='_compute_check_kind',
        store=True,
        readonly=False,
        default='third_party',
        copy=False,
        index=True,
    )

    @api.depends('payment_method_code')
    def _compute_check_kind(self):
        for rec in self:
            code = rec.payment_method_code
            if code == 'own_checks':
                rec.check_kind = 'own'
            elif code:
                rec.check_kind = 'third_party'
            else:
                rec.check_kind = rec.check_kind or 'third_party'

    # ── Check state (cobrado/pagado/girado) ─────────────────────────────────
    # One technical field with three values that apply to both kinds:
    # 'not_paid' / 'paid' (No cobrado/Cobrado for a third-party check,
    # No pagado/Pagado for an own one) and 'transferred' (Girado: a
    # third-party check endorsed to a supplier -- meaningless for an own
    # one, enforced below). A Selection can't vary its value labels per
    # view, so the two `check_state_third`/`check_state_own` fields below
    # mirror it with the right labels for each kind of list/form (stored, so
    # they can be grouped by).
    #
    # This is the only place check_state can be changed -- one check can
    # settle several pos.order/pos.payment at once (pay.freely.wizard), so it
    # can't live as an independently-writable field on pos.payment.
    # pos.payment.check_state mirrors this as a plain readonly `related`,
    # which Odoo keeps in sync automatically.
    check_state = fields.Selection(
        selection=[
            ('not_paid', 'No Cobrado / No Pagado'),
            ('paid', 'Cobrado / Pagado'),
            ('transferred', 'Girado'),
        ],
        string='Estado',
        default='not_paid',
        copy=False,
    )
    check_state_third = fields.Selection(
        selection=[('not_paid', 'No Cobrado'), ('paid', 'Cobrado'), ('transferred', 'Girado')],
        string='Estado de Cobro',
        compute='_compute_check_state_display',
        store=True,
    )
    check_state_own = fields.Selection(
        selection=[('not_paid', 'No Pagado'), ('paid', 'Pagado')],
        string='Estado de Pago',
        compute='_compute_check_state_display',
        store=True,
    )

    @api.depends('check_state', 'check_kind', 'issue_state')
    def _compute_check_state_display(self):
        for rec in self:
            is_own = rec.check_kind == 'own'
            rec.check_state_third = False if is_own else rec.check_state
            if not is_own:
                rec.check_state_own = False
            elif rec.issue_state == 'debited':
                # Own check cashed by the bank (its outstanding line got
                # reconciled against the statement): it is paid.
                rec.check_state_own = 'paid'
            else:
                rec.check_state_own = rec.check_state if rec.check_state != 'transferred' else False

    @api.constrains('check_state', 'check_kind')
    def _check_state_matches_check_kind(self):
        for rec in self:
            if rec.check_kind == 'own' and rec.check_state == 'transferred':
                raise ValidationError(_("Un cheque propio no puede estar Girado."))

    def _check_can_change_state(self):
        for rec in self:
            if rec.check_state == 'transferred':
                raise ValidationError(_(
                    "El cheque %(name)s ya fue girado: su estado no se puede cambiar.",
                    name=rec.name,
                ))

    def action_mark_paid(self):
        """Cobrado (third-party check) / Pagado (own check) -- the form is
        `edit="false"` by design (legal/audit document), so the state goes
        through these buttons instead of raw field editing."""
        self._check_can_change_state()
        self.write({'check_state': 'paid'})

    def action_mark_not_paid(self):
        self._check_can_change_state()
        self.write({'check_state': 'not_paid'})

    # ── POS orders paid with this check ─────────────────────────────────────
    # A check received from a customer settles one or more pos.order (one
    # pos.payment per order, all sharing the same check -- see
    # pos_payment.py/`pay.freely.wizard`): the orders the customer paid with
    # it, derived from those rows.
    pos_payment_ids = fields.One2many(
        comodel_name='pos.payment',
        inverse_name='l10n_latam_check_id',
        domain=[('pos_order_id', '!=', False)],
        string='Pagos de POS',
        readonly=True,
    )
    pos_order_ids = fields.Many2many(
        comodel_name='pos.order',
        string='Órdenes POS pagadas',
        compute='_compute_pos_payment_info',
    )
    pos_paid_amount = fields.Monetary(
        string='Aplicado a órdenes POS',
        compute='_compute_pos_payment_info',
    )

    @api.depends('pos_payment_ids.amount', 'pos_payment_ids.pos_order_id')
    def _compute_pos_payment_info(self):
        for check in self:
            payments = check.pos_payment_ids
            check.pos_order_ids = payments.pos_order_id
            check.pos_paid_amount = sum(payments.mapped('amount'))

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
