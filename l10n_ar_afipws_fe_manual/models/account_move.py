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
    l10n_ar_provisional_number = fields.Char(
        string="Número provisorio (pendiente ARCA)",
        copy=False,
        readonly=True,
    )
    display_name_manual = fields.Char(
        string="Número",
        compute="_compute_display_name_manual",
    )

    @api.depends("name", "l10n_ar_provisional_number")
    def _compute_display_name_manual(self):
        """name once ARCA confirmed it (or for anything outside this
        manual-AR flow); l10n_ar_provisional_number while still pending."""
        for move in self:
            if move.name and move.name != "/":
                move.display_name_manual = move.name
            else:
                move.display_name_manual = move.l10n_ar_provisional_number or move.name

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

    def _needs_provisional_number(self):
        self.ensure_one()
        return (
            self.env.context.get(_MANUAL_CONTEXT_KEY)
            and self.company_id.account_fiscal_country_id.code == "AR"
            and self.is_invoice()
            and self.move_type in ["out_invoice", "out_refund"]
            and bool(self.journal_id.afip_ws)
            and not self.afip_auth_code
        )

    def _set_next_sequence(self):
        """Override: while a manually-posted AR invoice hasn't been sent to
        ARCA yet, don't consume/reserve a real official number. Keep `name`
        as the standard Odoo placeholder ("/") and only expose a local,
        non-official preview (`l10n_ar_provisional_number`) computed the
        same way core would, so it never conflicts with the sequence chain
        of invoices actually confirmed by ARCA. The real `name` is only
        materialized (from ARCA's CbteDesde) in action_authorize_afip_manual,
        via the fe module's override of this same method."""
        self.ensure_one()
        if self._needs_provisional_number():
            # Reimplements _get_next_sequence_format() but without its
            # "brand new sequence -> seq forced to 0" reset: for AR/afip_ws
            # journals, _get_starting_sequence() already seeds the real last
            # known number (locally or from AFIP), so we always bump +1 from
            # whatever was parsed, be it a real previous local invoice or
            # that starting point. We never call _locked_increment() here
            # (that would reserve/consume a real slot) — this is preview only.
            last_sequence = self._get_last_sequence() or (
                self._get_last_sequence(relaxed=True) or self._get_starting_sequence()
            )
            format_string, format_values = self._get_sequence_format_param(last_sequence)
            format_values["seq"] += 1
            preview = format_string.format(**format_values)
            self.l10n_ar_provisional_number = "DRAFT-%s" % preview
            self.name = "/"
            return
        super()._set_next_sequence()

    def _post(self, soft=True):
        """Override: skip AFIP auto-send on post, except for invoices coming
        from POS (order._generate_pos_order_invoice already sets
        pos_order_ids on the move before calling _post), or for companies
        that opted out of manual authorization
        (company_id.l10n_ar_afipws_manual_auth = False). User must click
        'Enviar ARCA' for manually-created invoices otherwise."""
        from_pos = self.filtered("pos_order_ids")
        backend = self - from_pos
        manual = backend.filtered("company_id.l10n_ar_afipws_manual_auth")
        auto = backend - manual
        posted = self.env["account.move"]
        # From backend, company requires manual ARCA authorization
        if manual:
            posted |= super(
                AccountMove, manual.with_context(**{_MANUAL_CONTEXT_KEY: True})
            )._post(soft=soft)
        # From backend, company kept automatic authorization (standard
        # l10n_ar_afipws_fe behavior)
        if auto:
            posted |= super(AccountMove, auto)._post(soft=soft)
        # From POS
        if from_pos:
            posted |= super(AccountMove, from_pos)._post(soft=soft)
        return posted

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

        # Materialize the real, ARCA-confirmed number (was left as "/" +
        # l10n_ar_provisional_number preview at action_post time). Reuses the
        # fe module's _set_next_sequence override: since afip_auth_code and
        # afip_xml_response are now set, it reads CbteDesde straight from
        # ARCA's response instead of any locally-guessed number.
        for move in approved:
            move._set_next_sequence()
            move.l10n_ar_provisional_number = False

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
