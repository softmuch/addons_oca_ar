# Copyright 2024 - License LGPL-3.0

from odoo import models


class PosOrder(models.Model):
    _inherit = "pos.order"

    def _prepare_invoice_vals(self):
        """AFIP needs a responsibility type on the invoice partner to pick
        the document type (Factura A/B/C). If the customer selected on the
        order has none, or is explicitly "Consumidor Final", the invoice
        must go out to "Consumidor Final Anónimo" instead — without ever
        touching the customer chosen on the pos.order itself."""
        vals = super()._prepare_invoice_vals()
        if self.company_id.account_fiscal_country_id.code != "AR":
            return vals
        resp_type = self.partner_id.l10n_ar_afip_responsibility_type_id
        if not resp_type or resp_type == self.env.ref("l10n_ar.res_CF"):
            anonymous = self.env.ref("l10n_ar.par_cfa")
            vals["partner_id"] = anonymous.address_get(["invoice"])["invoice"]
            vals["partner_shipping_id"] = anonymous.address_get(["delivery"])["delivery"]
        return vals
