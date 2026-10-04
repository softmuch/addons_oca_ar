# For copyright and license notices, see __manifest__.py file in module root
# directory or check the readme files

from odoo import _, api, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Fields that define the fiscal identity and contact data of the partner.
    # Technical writes on other fields (followers, ranks, etc.) are still allowed
    # so that invoicing with the anonymous final consumer keeps working.
    _CFA_PROTECTED_FIELDS = (
        "name",
        "vat",
        "l10n_latam_identification_type_id",
        "l10n_ar_afip_responsibility_type_id",
        "is_company",
        "company_type",
        "parent_id",
        "active",
        "email",
        "phone",
        "mobile",
        "street",
        "street2",
        "city",
        "zip",
        "state_id",
        "country_id",
    )

    def _is_cfa_protected(self):
        """Return True if the anonymous final consumer partner (l10n_ar.par_cfa)
        is in self and the current context is not allowed to modify it."""
        if self.env.context.get("install_mode") or self.env.context.get(
            "l10n_ar_afipws_allow_cfa_write"
        ):
            return False
        cfa = self.env.ref("l10n_ar.par_cfa", raise_if_not_found=False)
        return bool(cfa and cfa in self)

    def write(self, vals):
        if self._is_cfa_protected() and any(
            fname in vals for fname in self._CFA_PROTECTED_FIELDS
        ):
            raise UserError(
                _(
                    "The partner 'Consumidor Final Anónimo' is used by AFIP "
                    "electronic invoicing and cannot be modified. "
                    "Create a new partner for this customer instead."
                )
            )
        return super().write(vals)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_cfa(self):
        if self._is_cfa_protected():
            raise UserError(
                _(
                    "The partner 'Consumidor Final Anónimo' is used by AFIP "
                    "electronic invoicing and cannot be deleted."
                )
            )
