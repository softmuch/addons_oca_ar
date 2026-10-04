# Copyright 2024 - License LGPL-3.0

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    l10n_ar_afipws_manual_auth = fields.Boolean(
        related="company_id.l10n_ar_afipws_manual_auth",
        readonly=False,
        string="Autorizar ARCA manualmente",
    )
    l10n_ar_pos_invoice_default = fields.Boolean(
        related="company_id.l10n_ar_pos_invoice_default",
        readonly=False,
        string="Factura activada por defecto en POS",
    )
    l10n_ar_pos_invoice_download = fields.Boolean(
        related="company_id.l10n_ar_pos_invoice_download",
        readonly=False,
        string="Descargar PDF de factura en POS",
    )
