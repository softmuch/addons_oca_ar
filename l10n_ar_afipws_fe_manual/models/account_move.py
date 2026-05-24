# Copyright 2024 - License LGPL-3.0

import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

_MANUAL_CONTEXT_KEY = "l10n_ar_afipws_fe_manual"


class AccountMove(models.Model):
    _inherit = "account.move"

    needs_afip_auth = fields.Boolean(
        compute="_compute_needs_afip_auth",
        string="Necesita autorización ARCA",
    )

    @api.depends(
        "state",
        "journal_id.afip_ws",
        "afip_auth_code",
        "move_type",
        "company_id.account_fiscal_country_id",
    )
    def _compute_needs_afip_auth(self):
        for move in self:
            move.needs_afip_auth = (
                move.state == "posted"
                and move.company_id.account_fiscal_country_id.code == "AR"
                and move.is_invoice()
                and move.move_type in ["out_invoice", "out_refund"]
                and bool(move.journal_id.afip_ws)
                and not move.afip_auth_code
            )

    def _post(self, soft=True):
        """Override: skip AFIP auto-send on post. User must click 'Enviar ARCA'."""
        return super(
            AccountMove, self.with_context(**{_MANUAL_CONTEXT_KEY: True})
        )._post(soft=soft)

    def authorize_afip(self):
        """Override: no-op when called from _post (context flag set).
        Normal behavior when called from action_authorize_afip_manual."""
        if self.env.context.get(_MANUAL_CONTEXT_KEY):
            _logger.info(
                "l10n_ar_afipws_fe_manual: skipping auto AFIP send for %s invoice(s)",
                len(self),
            )
            return self.env["account.move"], self.env["account.move"]
        return super().authorize_afip()

    def action_authorize_afip_manual(self):
        """Button (form) and server action (list): manually authorize posted invoice(s).

        - Single invoice + rejection  → UserError (prominent dialog).
        - Multiple invoices           → notification with approved/rejected summary.
        - Single invoice + approved   → success notification.
        """
        to_authorize = self.filtered(
            lambda x: x.company_id.account_fiscal_country_id.code == "AR"
            and x.is_invoice()
            and x.move_type in ["out_invoice", "out_refund"]
            and x.journal_id.afip_ws
            and not x.afip_auth_code
            and x.state == "posted"
        )
        if not to_authorize:
            raise UserError(
                _("No hay facturas confirmadas pendientes de autorización ARCA.")
            )

        approved, rejected = to_authorize.authorize_afip()

        # Single invoice rejected → raise so error shows prominently in form
        if len(self) == 1 and rejected:
            raise UserError(
                _("ARCA rechazó la factura:\n%s")
                % (rejected.afip_message or _("Error desconocido"))
            )

        # Build summary lines
        lines = []
        if approved:
            lines.append(_("✓ %d factura(s) autorizada(s).") % len(approved))
        if rejected:
            details = "\n".join(
                "• %s: %s" % (inv.name, inv.afip_message or _("Error desconocido"))
                for inv in rejected
            )
            lines.append(_("✗ %d factura(s) rechazada(s):\n%s") % (len(rejected), details))

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Resultado ARCA"),
                "message": "\n".join(lines),
                "type": "warning" if rejected else "success",
                "sticky": bool(rejected),
            },
        }
