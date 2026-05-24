# Copyright 2024 - License LGPL-3.0

{
    "name": "Factura Electrónica AR - Envío Manual ARCA",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations",
    "author": "Custom",
    "license": "LGPL-3",
    "summary": "Deshabilita el envío automático a ARCA al confirmar factura. "
               "Agrega botón 'Enviar ARCA' manual.",
    "depends": ["l10n_ar_afipws_fe"],
    "data": [
        "views/account_move_view.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
