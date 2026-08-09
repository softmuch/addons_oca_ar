from odoo import models


class PosPaymentMethod(models.Model):
    _inherit = "pos.payment.method"

    def _get_payment_method_type(self):
        return super()._get_payment_method_type() + [("check", "Cheque")]
