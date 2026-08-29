from odoo import _, fields, models
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
        help="Cheque contable generado al cerrar la sesión de POS.",
    )

    def action_create_l10n_latam_check(self):
        self.ensure_one()
        if self.payment_method_id.payment_method_type != 'check':
            raise UserError(_("Este pago no es de tipo cheque."))
        if self.l10n_latam_check_id:
            raise UserError(_("Este pago ya tiene un cheque asociado."))
        if self.session_id.state != 'closed':
            raise UserError(_(
                "Solo se puede crear el cheque manualmente si la sesión ya está "
                "cerrada. Con la sesión abierta, el cheque se genera solo al cerrarla."
            ))
        if not self.l10n_latam_check_number:
            raise UserError(_("Completá los datos del cheque antes de crearlo."))

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
            'l10n_latam_new_check_ids': [session._get_l10n_latam_check_vals(self)],
        })
        session._link_l10n_latam_checks(account_payment, self)
        session._ensure_payment_outstanding_account(account_payment, self.amount)
        account_payment.action_post()
        return account_payment._get_records_action()
