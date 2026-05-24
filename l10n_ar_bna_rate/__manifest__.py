# Copyright 2024 - License LGPL-3.0

{
    "name": "Cotización USD - Banco Nación Argentina (BNA)",
    "version": "19.0.1.0.0",
    "category": "Accounting/Localizations",
    "author": "Custom",
    "license": "LGPL-3",
    "summary": "Actualiza automáticamente la cotización USD/ARS "
               "desde la tabla Divisas del Banco Nación Argentina.",
    "depends": ["base"],
    "external_dependencies": {
        "python": ["requests", "bs4"],
    },
    "data": [
        "data/bna_rate_cron.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": False,
}
