from odoo import _, api, fields, models
from odoo.exceptions import UserError


class PosPayment(models.Model):
    _inherit = "pos.payment"

    # Mirrored onto self so view `invisible` expressions can reference it
    # directly (`payment_method_type != 'check'`) instead of the dotted path
    # `payment_method_id.payment_method_type` -- the webclient's onchange/read
    # field spec only ever fetches `display_name` for a plain many2one unless
    # a sub-field is a real field of the record itself, so the dotted form
    # silently never evaluates true and the check fields never show.
    payment_method_type = fields.Selection(related='payment_method_id.payment_method_type')

    l10n_latam_check_number = fields.Char(string="Número de Cheque")
    l10n_latam_check_bank_id = fields.Many2one("res.bank", string="Banco Emisor")
    l10n_latam_check_issuer_vat = fields.Char(string="CUIT Emisor")
    l10n_latam_check_type = fields.Selection(
        selection=[
            ("common", "Cheque Común"),
            ("deferred", "Cheque de Pago Diferido (CPD)"),
        ],
        string="Tipo de Cheque",
    )
    l10n_latam_check_issue_date = fields.Date(string="Fecha de Emisión")
    l10n_latam_check_payment_date = fields.Date(string="Fecha de Cobro")
    l10n_latam_check_id = fields.Many2one(
        "l10n_latam.check", string="Cheque", readonly=True, copy=False,
        help="Cheque contable. Se crea instantáneamente en cuanto el pago "
             "tiene el número de cheque cargado -- no espera al cierre de "
             "sesión ni a que la orden se facture.",
    )
    # Mirrored for the same reason as `payment_method_type` above: a view
    # `invisible` expression can't reliably read `l10n_latam_check_id.payment_id`
    # (dotted path off a many2one) -- the client only ever fetches
    # `display_name` for that many2one unless the sub-field is a real field
    # of this record itself.
    l10n_latam_check_payment_id = fields.Many2one(
        "account.payment", related="l10n_latam_check_id.payment_id",
    )
    # pos.payment only ever represents a check *received* from the customer
    # (POS never issues its own check), so only the "cliente" pair applies
    # here -- l10n_latam.check carries the full 4-value selection since it
    # also covers own-checks issued outside the POS.
    check_state = fields.Selection(
        selection=[
            ("not_collected", "No Cobrado"),
            ("collected", "Cobrado"),
        ],
        string="Estado del Cheque",
        default="not_collected",
        copy=False,
    )

    @api.onchange('payment_method_id')
    def _onchange_payment_method_id_l10n_latam_check(self):
        """Suggest the order's own partner CUIT as the check issuer's -- the
        cashier/backoffice can still edit it, this is just a convenient
        default for the (very common) case where the customer is paying
        with their own check.
        """
        if (
            self.payment_method_id.payment_method_type == 'check'
            and not self.l10n_latam_check_issuer_vat
            and self.pos_order_id.partner_id.vat
        ):
            self.l10n_latam_check_issuer_vat = self.pos_order_id.partner_id.vat

    @api.model
    def _l10n_latam_check_require_real_partner(self, partner):
        """A check payment must be traceable to a real customer -- raise if
        `partner` is empty or is the "Consumidor Final Anónimo" walk-in
        customer (`l10n_ar.par_cfa`, loaded into the POS frontend as
        `pos.config._consumidor_final_anonimo_id` -- see
        `l10n_ar_pos/models/pos_config.py`). `raise_if_not_found=False` in
        case `l10n_ar` isn't installed; a plain "must pick someone" check is
        still applied either way.
        """
        anonymous = self.env.ref('l10n_ar.par_cfa', raise_if_not_found=False)
        if not partner or (anonymous and partner.id == anonymous.id):
            raise UserError(_(
                "Elegí un cliente distinto de \"Consumidor Final Anónimo\" "
                "antes de cargar un pago con cheque."
            ))

    def _create_payment_moves(self, is_reverse=False):
        """Core calls this at invoice-checkout time (`pos.order.
        _generate_pos_order_invoice`) to create each payment's account.move
        and reconcile it against the invoice right away. Check payments
        never get an account.move/account.payment at that point -- only
        later, at session close, and only then (see `pos.session.
        _create_combine_account_payment`/`_create_invoiced_check_account_payment`
        below). The invoice's own receivable line for a check payment stays
        open/unreconciled until the session actually closes -- intentional:
        a third-party check isn't considered truly settled until it's
        actually processed at that point.
        """
        check_payments = self.filtered(lambda p: p.payment_method_id.payment_method_type == 'check')
        other_payments = self - check_payments
        if not other_payments:
            return self.env['account.move']
        return super(PosPayment, other_payments)._create_payment_moves(is_reverse)

    def create(self, vals_list):
        payments = super().create(vals_list)
        payments._l10n_latam_ensure_check()
        return payments

    def write(self, vals):
        res = super().write(vals)
        self._l10n_latam_ensure_check()
        if 'check_state' in vals and not self.env.context.get('skip_check_state_sync'):
            for payment in self:
                if payment.l10n_latam_check_id and payment.l10n_latam_check_id.check_state != payment.check_state:
                    payment.l10n_latam_check_id.with_context(skip_check_state_sync=True).write(
                        {'check_state': payment.check_state}
                    )
        return res

    def _l10n_latam_ensure_check(self):
        """Create the `l10n_latam.check` instantly, always, for any check
        payment that has its number filled in -- regardless of whether the
        order is invoiced, and without waiting for session close (see
        `pos.session._create_combine_account_payment`/
        `_create_split_account_payment` below, which only create the
        `account.payment` later, for invoiced orders, and link it to this
        same check instead of creating a new one).

        `l10n_latam.check.payment_id` is redefined as non-required in this
        module (models/l10n_latam_check.py) precisely to allow this: no
        account.payment exists yet at this point.
        """
        for payment in self:
            if (
                payment.payment_method_id.payment_method_type == 'check'
                and payment.l10n_latam_check_number
                and not payment.l10n_latam_check_id
            ):
                self._l10n_latam_check_require_real_partner(payment.partner_id)
                check_vals = payment.session_id._get_l10n_latam_check_vals(payment)[2]
                # `payment_date` is required on l10n_latam.check itself; the
                # cashier may not have filled in "Fecha de Cobro" yet, but
                # the check must still be created right now regardless --
                # fall back to the payment's own date rather than leaving
                # this required field empty.
                if not check_vals.get('payment_date'):
                    check_vals['payment_date'] = (
                        fields.Date.to_date(payment.payment_date) if payment.payment_date
                        else fields.Date.today()
                    )
                # `company_id` is `related='payment_id.company_id', store=True`
                # on l10n_latam.check -- with no payment_id yet, that compute
                # gives False. Set it explicitly from the pos.payment itself
                # so the check isn't companyless until the account.payment
                # eventually gets created.
                check_vals['company_id'] = payment.company_id.id
                # Same story as `company_id` above, but for `partner_id`
                # (also redefined store=True, readonly=False in
                # l10n_latam_check.py): always the order's own customer,
                # front or back, regardless of invoicing/payment_id.
                check_vals['partner_id'] = payment.partner_id.id
                # Keep both records in sync from the moment the check is
                # born (same default value on both fields, but explicit here
                # in case the cashier already flipped it before this runs,
                # e.g. editing the inline list before the number was final).
                check_vals['check_state'] = payment.check_state
                check = self.env['l10n_latam.check'].sudo().create(check_vals)
                payment.l10n_latam_check_id = check.id

    def action_create_l10n_latam_check(self):
        """Manually create the account.payment for a check whose order was
        never invoiced, or whose session already closed before it could be
        auto-processed (see `pos.session._create_combine_account_payment` in
        this module, which normally does this automatically at session
        close for invoiced orders only).

        The `l10n_latam.check` itself already exists by this point (created
        instantly on the payment, see `_l10n_latam_ensure_check` above) --
        this only creates the missing account.payment and links it.
        """
        self.ensure_one()
        if self.payment_method_id.payment_method_type != 'check':
            raise UserError(_("Este pago no es de tipo cheque."))
        if not self.l10n_latam_check_number:
            raise UserError(_("Completá los datos del cheque antes de crearlo."))
        if not self.l10n_latam_check_id:
            raise UserError(_("Este pago todavía no tiene un cheque creado."))
        if self.l10n_latam_check_id.payment_id:
            raise UserError(_("Este cheque ya tiene un pago contable asociado."))
        if self.session_id.state != 'closed':
            raise UserError(_(
                "Solo se puede crear el pago contable manualmente si la sesión ya está cerrada."
            ))

        session = self.session_id
        payment_method = self.payment_method_id
        if not payment_method.journal_id:
            raise UserError(_("El método de pago no tiene diario configurado."))

        accounting_partner = self.env['res.partner']._find_accounting_partner(self.partner_id)
        payment_type = 'inbound' if self.currency_id.compare_amounts(self.amount, 0) >= 0 else 'outbound'
        account_payment = self.env['account.payment'].create({
            'amount': abs(self.amount),
            'partner_id': accounting_partner.id,
            'journal_id': payment_method.journal_id.id,
            'force_outstanding_account_id': payment_method.outstanding_account_id.id,
            'destination_account_id': accounting_partner.property_account_receivable_id.id,
            'memo': _('%(payment_method)s POS payment of %(partner)s in %(session)s',
                      payment_method=payment_method.name, partner=self.partner_id.display_name, session=session.name),
            'pos_payment_method_id': payment_method.id,
            'pos_session_id': session.id,
            'payment_type': payment_type,
        })
        self.l10n_latam_check_id.payment_id = account_payment.id
        self.account_move_id = account_payment.move_id.id
        session._ensure_payment_outstanding_account(account_payment, self.amount)
        account_payment.action_post()
        return account_payment._get_records_action()
