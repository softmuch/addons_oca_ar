{
    "name": "Extensión Cheques LATAM",
    "version": "19.0.1.0.1",
    "category": "Localization/Argentina",
    "website": "https://github.com/OCA/l10n-argentina",
    "author": "Odossey",
    "license": "AGPL-3",
    "summary": "Extiende l10n_latam.check con tipo, fecha de emisión, alertas de vencimiento y pago con cheque en el POS",
    "depends": [
        "l10n_latam_check",
        "account",
        "point_of_sale",
    ],
    "data": [
        "data/ir_cron_data.xml",
        "views/l10n_latam_check_ext_views.xml",
        "views/res_config_settings_views.xml",
        "views/pos_payment_views.xml",
        "views/pos_order_views.xml",
        "views/pos_menu_views.xml",
    ],
    "assets": {
        "point_of_sale._assets_pos": [
            "l10n_latam_check_ext/static/src/**/*",
        ],
    },
    "installable": True,
    "auto_install": False,
    "application": False,
}
