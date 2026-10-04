# Copyright 2024 - License LGPL-3.0

from odoo import api, fields, models


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
    l10n_ar_pos_invoice_default = fields.Boolean(
        string="Factura activada por defecto en POS",
        default=False,
        help="Define el estado inicial del botón 'Factura' en la pantalla de "
        "pago del Punto de Venta.\n"
        "Si está activo, cada orden llega a la pantalla de pago con 'Factura' "
        "marcado (comportamiento estándar de l10n_ar_pos).\n"
        "Si está desactivo, 'Factura' queda desmarcado y el cajero lo activa "
        "solo cuando el cliente pide factura.",
    )
    l10n_ar_pos_invoice_download = fields.Boolean(
        string="Descargar PDF de factura en POS",
        default=False,
        help="Si está activo, al validar en el Punto de Venta una orden con "
        "'Factura' marcado se descarga automáticamente el PDF de la factura "
        "(comportamiento estándar de Odoo).\n"
        "Si está desactivo, la factura se genera igual pero no se descarga: "
        "queda disponible en Contabilidad y en la orden del POS.",
    )

    @api.model
    def _load_pos_data_fields(self, config_id):
        return super()._load_pos_data_fields(config_id) + [
            "l10n_ar_pos_invoice_default",
            "l10n_ar_pos_invoice_download",
        ]
