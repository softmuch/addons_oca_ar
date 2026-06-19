{
    "name": "Extensión Cheques LATAM",
    "version": "19.0.1.0.0",
    "category": "Localization/Argentina",
    "website": "https://github.com/OCA/l10n-argentina",
    "author": "Odossey",
    "license": "AGPL-3",
    "summary": "Extiende l10n_latam.check con tipo, fecha de emisión y alertas de vencimiento",
    "depends": [
        "l10n_latam_check",
        "account",
    ],
    "data": [
        "data/ir_cron_data.xml",
        "views/l10n_latam_check_ext_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
