from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Defaults used when the company issues one of its OWN checks (the
    # purchase payment wizards, "Pagar" / "Pagar Libremente", `check_mode =
    # 'new'`): they're set on the company's own partner
    # (`company.partner_id`), next to its bank accounts (`bank_ids`).
    default_bank_id = fields.Many2one(
        comodel_name='res.partner.bank',
        string='Cuenta bancaria para cheques',
        domain="[('partner_id', '=', id)]",
        help="Cuenta bancaria (de las definidas en 'Cuentas bancarias') cuyo banco se "
        "propone por defecto como banco emisor al emitir un cheque propio.",
    )
    default_check_type = fields.Selection(
        selection='_selection_default_check_type',
        string='Tipo de cheque por defecto',
        help="Tipo de cheque que se propone por defecto al emitir un cheque propio.",
    )

    @api.model
    def _selection_default_check_type(self):
        return self.env['l10n_latam.check']._fields['check_type'].selection

    @api.constrains('default_bank_id')
    def _check_default_bank_id(self):
        for partner in self:
            if partner.default_bank_id and partner.default_bank_id not in partner.bank_ids:
                raise ValidationError(_(
                    "La cuenta bancaria por defecto debe ser una de las cuentas bancarias "
                    "de %(partner)s.", partner=partner.display_name,
                ))
