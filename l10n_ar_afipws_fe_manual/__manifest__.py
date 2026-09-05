# Copyright 2024 - License LGPL-3.0

{
    "name": "Factura Electrónica AR - Envío Manual ARCA",
    "version": "19.0.1.0.0",
    "category": "Accounting/Localizations",
    "author": "Custom",
    "license": "LGPL-3",
    "summary": "Deshabilita el envío automático a ARCA al confirmar factura. "
               "Agrega botón 'Enviar ARCA' manual.",
    "depends": ["l10n_ar_afipws_fe", "l10n_ar_pos"],
    "data": [
        "views/account_move_view.xml",
        "views/res_config_settings.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "l10n_ar_afipws_fe_manual/static/src/payment_screen_patch.js",
            "l10n_ar_afipws_fe_manual/static/src/pos_order_patch.js",
        ],
    },
    "installable": True,
    "auto_install": False,
    "application": False,
}
