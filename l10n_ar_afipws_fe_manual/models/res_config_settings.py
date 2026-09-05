# Copyright 2024 - License LGPL-3.0

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    l10n_ar_afipws_manual_auth = fields.Boolean(
        related="company_id.l10n_ar_afipws_manual_auth",
        readonly=False,
        string="Autorizar ARCA manualmente",
    )
