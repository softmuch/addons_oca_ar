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

    def _bna_fetch_usd_rate(self):
        """Scrape USD venta rate from BNA divisas table.

        Returns:
            dict with keys 'compra' and 'venta' (floats, ARS per 1 USD)

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

        # BNA renders two tables: id="divisas" y id="billetes"
        container = soup.find(id=BNA_TABLE_ID)
        if not container:
            raise UserError(
                _(
                    "No se encontró la tabla '%s' en %s. "
                    "El BNA puede haber cambiado su sitio web."
                )
                % (BNA_TABLE_ID, BNA_URL)
            )

        tbody = container.find("table")
        if not tbody:
            raise UserError(
                _("Tabla '%s' encontrada pero no contiene <table> HTML.") % BNA_TABLE_ID
            )

        rows = tbody.find_all("tr")

        for row in rows:
            cols = [td.get_text(strip=True) for td in row.find_all("td")]
            if len(cols) < 3:
                continue

            currency_label = cols[0].lower()
            # BNA labels USD como "Dólar U.S.A.", "U$S", "Dolar", etc.
            if any(kw in currency_label for kw in ("dólar", "dolar", "u$s", "usd")):
                try:
                    compra = self._bna_parse_number(cols[1])
                    venta = self._bna_parse_number(cols[2])
                    _logger.info(
                        "BNA scrape OK — USD billetes: compra=%.4f venta=%.4f",
                        compra,
                        venta,
                    )
                    return {"compra": compra, "venta": venta}
                except (ValueError, IndexError) as e:
                    raise UserError(
                        _("Error al parsear cotización USD del BNA: %s\nColumnas: %s")
                        % (str(e), cols)
                    )

        raise UserError(
            _(
                "No se encontró la fila de USD en la tabla '%s' del BNA. "
                "Columnas encontradas: %s"
            )
            % (BNA_TABLE_ID, [r.get_text(strip=True) for r in rows[:5]])
        )

    def _bna_update_rates(self):
        """Fetch BNA USD/ARS rate and update res.currency.rate for all ARS companies.

        Only updates companies whose base currency is ARS.
        Creates one rate record per company per day (updates if already exists).
        """
        usd_data = self._bna_fetch_usd_rate()
        bna_venta = usd_data["venta"]
        today = date.today()

        usd_currency = self.sudo().search([("name", "=", "USD")], limit=1)
        if not usd_currency:
            _logger.warning("l10n_ar_bna_rate: moneda USD no encontrada en Odoo.")
            return False

        # rate = unidades de USD por 1 ARS = 1 / (ARS por USD)
        # Odoo almacena el rate como "esta moneda por 1 unidad de la moneda base"
        # Si base = ARS → rate USD = 1 / venta_bna
        rate_value = 1.0 / bna_venta

        CurrencyRate = self.env["res.currency.rate"].sudo()
        companies = self.env["res.company"].sudo().search([])
        updated = 0

        for company in companies:
            if company.currency_id.name != "ARS":
                continue

            existing = CurrencyRate.search(
                [
                    ("currency_id", "=", usd_currency.id),
                    ("name", "=", today),
                    ("company_id", "=", company.id),
                ],
                limit=1,
            )

            if existing:
                existing.rate = rate_value
                _logger.info(
                    "BNA rate updated — empresa: %s | venta: %.4f → rate: %.8f",
                    company.name,
                    bna_venta,
                    rate_value,
                )
            else:
                CurrencyRate.create(
                    {
                        "currency_id": usd_currency.id,
                        "name": today,
                        "rate": rate_value,
                        "company_id": company.id,
                    }
                )
                _logger.info(
                    "BNA rate created — empresa: %s | venta: %.4f → rate: %.8f",
                    company.name,
                    bna_venta,
                    rate_value,
                )
            updated += 1

        if not updated:
            _logger.warning(
                "l10n_ar_bna_rate: ninguna empresa con moneda ARS encontrada."
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
                    "Cotización USD/ARS del Banco Nación Argentina actualizada correctamente."
                ),
                "type": "success",
                "sticky": False,
            },
        }
