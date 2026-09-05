# Copyright 2024 - License LGPL-3.0

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    l10n_ar_afipws_manual_auth = fields.Boolean(
        string="Autorizar ARCA manualmente",
        default=True,
        help="Si está activo, al confirmar una factura (action_post) NO se "
        "envía automáticamente a ARCA: la factura queda con un número "
        "provisorio ('DRAFT-...') hasta que se presiona el botón "
        "'Enviar ARCA' (action_authorize_afip_manual), momento en el que "
        "se asigna el número oficial confirmado por ARCA.\n"
        "Si está desactivo, se vuelve al comportamiento estándar de "
        "l10n_ar_afipws_fe: autorización automática contra ARCA al "
        "confirmar la factura.\n"
        "No aplica a facturas generadas desde el Punto de Venta (POS), que "
        "siempre se autorizan en el momento.",
    )
