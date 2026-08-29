from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero


class PosMakePayment(models.TransientModel):
    _inherit = 'pos.make.payment'

    # Same reasoning as pos.payment's own mirrored field: the dotted path
    # `payment_method_id.payment_method_type` in an `invisible` expression
    # never gets fetched by the client's onchange/read spec (confirmed via
    # the actual RPC payload -- only `display_name` is requested for the
    # many2one), so the check fields would stay hidden forever without this.
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

    def _l10n_latam_check_validate(self, payment_method):
        """Raise if this is a check payment with no check number.

        Called from every `check()` override that can create a payment on
        this wizard -- core's own path (below) AND
        `odossey_partial_payments_pos`'s (for a `partially_paid` order,
        which takes over `check()` entirely and never reaches this one).
        """
        if payment_method.payment_method_type == 'check' and not self.l10n_latam_check_number:
            raise UserError(_("Completá el número de cheque antes de continuar."))

    def _l10n_latam_check_payment_vals(self, payment_method):
        """Extra `pos.payment` create vals for a check payment, or `{}`.

        Duck-typed extension point: any other `check()` override (see
        `odossey_partial_payments_pos`) can call
        `getattr(self, '_l10n_latam_check_payment_vals', lambda pm: {})(payment_method)`
        to pick this up without depending on this (AR-only) module.
        """
        if payment_method.payment_method_type != 'check':
            return {}
        return {
            'l10n_latam_check_number': self.l10n_latam_check_number,
            'l10n_latam_check_bank_id': self.l10n_latam_check_bank_id.id,
            'l10n_latam_check_issuer_vat': self.l10n_latam_check_issuer_vat,
            'l10n_latam_check_type': self.l10n_latam_check_type,
            'l10n_latam_check_issue_date': self.l10n_latam_check_issue_date,
            'l10n_latam_check_payment_date': self.l10n_latam_check_payment_date,
        }

    def check(self):
        """Full override of core's `check()`.

        Core builds the `pos.payment` create vals from `self.read()` and
        passes them straight to `order.add_payment(data)` inside this same
        method body -- there is no hook to inject the check fields into that
        dict from outside, so this duplicates the method instead of calling
        super(). Keep in sync with `point_of_sale/wizard/pos_payment.py`'s
        `check()` if core changes it.

        NOTE: this only runs for orders NOT in state 'partially_paid' --
        `odossey_partial_payments_pos`'s own `check()` override takes over
        entirely for those (see `_l10n_latam_check_validate`/
        `_l10n_latam_check_payment_vals` above, called from there too).
        """
        self.ensure_one()
        order = self.env['pos.order'].browse(self.env.context.get('active_id', False))
        if self.payment_method_id.split_transactions and not order.partner_id:
            raise UserError(_(
                "Customer is required for %s payment method.",
                self.payment_method_id.name,
            ))

        currency = order.currency_id
        init_data = self.read()[0]
        payment_method = self.env['pos.payment.method'].browse(init_data['payment_method_id'][0])
        self._l10n_latam_check_validate(payment_method)
        if not float_is_zero(init_data['amount'], precision_rounding=currency.rounding):
            payment_vals = {
                'pos_order_id': order.id,
                'amount': order._get_rounded_amount(
                    init_data['amount'], payment_method.is_cash_count or not self.config_id.only_round_cash_method,
                ),
                'name': init_data['payment_name'],
                'payment_method_id': init_data['payment_method_id'][0],
            }
            payment_vals.update(self._l10n_latam_check_payment_vals(payment_method))
            order.add_payment(payment_vals)

        if order.state == 'draft' and order._is_pos_order_paid():
            order._process_saved_order(False)
            if order.state in {'paid', 'done'}:
                order._send_order()
                order.config_id.notify_synchronisation(order.config_id.current_session_id.id, 0)
            return {'type': 'ir.actions.act_window_close'}

        return self.launch_payment()
