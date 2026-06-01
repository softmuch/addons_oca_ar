# Copyright 2024 - License LGPL-3.0

import logging
from datetime import date

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BNA_URL = "https://www.bna.com.ar/"
# "divisas" = cotización transferencias (uso empresarial)
# "billetes" = cotización efectivo/billetes físicos
BNA_TABLE_ID = "billetes"


class ResCurrency(models.Model):
    _inherit = "res.currency"

    @staticmethod
    def _bna_parse_number(value):
        """Parse BNA number string to float.

        BNA formats observed:
          '1394.0000'   → dot = decimal separator  → 1394.0
          '1.394,0000'  → dot = thousands, comma = decimal → 1394.0
          '1394,0000'   → comma = decimal → 1394.0
        """
        value = value.strip()
        has_dot = "." in value
        has_comma = "," in value

        if has_dot and has_comma:
            # Format: 1.394,0000  →  remove dot, replace comma
            value = value.replace(".", "").replace(",", ".")
        elif has_comma and not has_dot:
            # Format: 1394,0000  →  replace comma
            value = value.replace(",", ".")
        # else: dot is decimal or plain integer — use as-is

        return float(value)

    # Monedas a scrapear: código Odoo → keywords a buscar en la columna del BNA
    _BNA_CURRENCIES = {
        "USD": ("dólar", "dolar", "u$s", "usd"),
        "EUR": ("euro",),
        "BRL": ("real",),
    }

    def _bna_fetch_rates(self):
        """Scrape venta rates for USD, EUR and BRL from BNA billetes table.

        Returns:
            dict  { 'USD': {'compra': float, 'venta': float}, 'EUR': {...}, 'BRL': {...} }

        Raises:
            UserError on connection error or parsing failure.
        """
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError as e:
            raise UserError(
                _("Dependencia faltante: %s\nInstalar: pip install requests beautifulsoup4")
                % str(e)
            )

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(compatible; Odoo/BNA-Rate-Updater)"
            ),
            "Accept-Language": "es-AR,es;q=0.9",
        }

        try:
            response = requests.get(BNA_URL, headers=headers, timeout=15)
            response.raise_for_status()
        except Exception as e:
            raise UserError(_("Error al conectar con BNA (%s): %s") % (BNA_URL, str(e)))

        soup = BeautifulSoup(response.text, "html.parser")

        container = soup.find(id=BNA_TABLE_ID)
        if not container:
            raise UserError(
                _(
                    "No se encontró la tabla '%s' en %s. "
                    "El BNA puede haber cambiado su sitio web."
                )
                % (BNA_TABLE_ID, BNA_URL)
            )

        table = container.find("table")
        if not table:
            raise UserError(
                _("Tabla '%s' encontrada pero no contiene <table> HTML.") % BNA_TABLE_ID
            )

        rows = table.find_all("tr")
        result = {}

        for row in rows:
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) < 3:
                continue

            label = cols[0].lower()
            for odoo_code, keywords in self._BNA_CURRENCIES.items():
                if odoo_code in result:
                    continue
                if any(kw in label for kw in keywords):
                    try:
                        compra = self._bna_parse_number(cols[1])
                        venta = self._bna_parse_number(cols[2])
                        result[odoo_code] = {"compra": compra, "venta": venta}
                        _logger.info(
                            "BNA scrape OK — %s billetes: compra=%.4f venta=%.4f",
                            odoo_code, compra, venta,
                        )
                    except (ValueError, IndexError) as e:
                        raise UserError(
                            _("Error al parsear cotización %s del BNA: %s\nColumnas: %s")
                            % (odoo_code, str(e), cols)
                        )

        missing = [c for c in self._BNA_CURRENCIES if c not in result]
        if missing:
            _logger.warning(
                "l10n_ar_bna_rate: no se encontraron filas para %s en tabla '%s'.",
                missing, BNA_TABLE_ID,
            )

        if not result:
            raise UserError(
                _(
                    "No se encontró ninguna cotización en la tabla '%s' del BNA. "
                    "Columnas encontradas: %s"
                )
                % (BNA_TABLE_ID, [r.get_text(strip=True) for r in rows[:5]])
            )

        return result

    def _bna_update_rates(self):
        """Fetch BNA rates and update res.currency.rate for USD, EUR and BRL.

        Only updates companies whose base currency is ARS.
        Creates one rate record per currency per company per day (updates if exists).
        """
        rates_data = self._bna_fetch_rates()
        today = date.today()

        CurrencyRate = self.env["res.currency.rate"].sudo()
        companies = self.env["res.company"].sudo().search([])
        ars_companies = [c for c in companies if c.currency_id.name == "ARS"]

        if not ars_companies:
            _logger.warning("l10n_ar_bna_rate: ninguna empresa con moneda ARS encontrada.")
            return False

        for odoo_code, data in rates_data.items():
            venta = data["venta"]
            # Odoo rate = unidades de esta moneda por 1 unidad de la moneda base (ARS)
            # → rate = 1 / venta_bna
            rate_value = 1.0 / venta

            currency = self.sudo().search([("name", "=", odoo_code)], limit=1)
            if not currency:
                _logger.warning("l10n_ar_bna_rate: moneda %s no encontrada en Odoo.", odoo_code)
                continue

            for company in ars_companies:
                existing = CurrencyRate.search(
                    [
                        ("currency_id", "=", currency.id),
                        ("name", "=", today),
                        ("company_id", "=", company.id),
                    ],
                    limit=1,
                )

                if existing:
                    existing.rate = rate_value
                    _logger.info(
                        "BNA rate updated — %s | empresa: %s | venta: %.4f → rate: %.8f",
                        odoo_code, company.name, venta, rate_value,
                    )
                else:
                    CurrencyRate.create(
                        {
                            "currency_id": currency.id,
                            "name": today,
                            "rate": rate_value,
                            "company_id": company.id,
                        }
                    )
                    _logger.info(
                        "BNA rate created — %s | empresa: %s | venta: %.4f → rate: %.8f",
                        odoo_code, company.name, venta, rate_value,
                    )

        return True

    def action_bna_update_rates(self):
        """Manual action: update BNA rates immediately and show notification."""
        self._bna_update_rates()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("BNA - Cotización actualizada"),
                "message": _(
                    "Cotizaciones USD, EUR y BRL del Banco Nación Argentina actualizadas correctamente."
                ),
                "type": "success",
                "sticky": False,
            },
        }
