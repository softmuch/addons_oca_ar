from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    l10n_latam_own_check_alert_days = fields.Integer(
        related='company_id.l10n_latam_own_check_alert_days',
        readonly=False,
        string='Días de aviso (cheques propios)',
    )
    l10n_latam_own_check_alert_user_ids = fields.Many2many(
        related='company_id.l10n_latam_own_check_alert_user_ids',
        readonly=False,
        string='Usuarios a notificar (cheques propios)',
    )
    l10n_latam_third_check_alert_days = fields.Integer(
        related='company_id.l10n_latam_third_check_alert_days',
        readonly=False,
        string='Días de aviso (cheques de terceros)',
    )
    l10n_latam_third_check_alert_user_ids = fields.Many2many(
        related='company_id.l10n_latam_third_check_alert_user_ids',
        readonly=False,
        string='Usuarios a notificar (cheques de terceros)',
    )

    # Defaults for the company's own issued checks: they live on the company's
    # own partner (see res_partner.py).
    l10n_latam_company_partner_id = fields.Many2one(related='company_id.partner_id')
    l10n_latam_default_check_bank_id = fields.Many2one(
        related='company_id.partner_id.default_bank_id',
        readonly=False,
        domain="[('partner_id', '=', l10n_latam_company_partner_id)]",
        string='Cuenta bancaria para cheques',
    )
    l10n_latam_default_check_type = fields.Selection(
        related='company_id.partner_id.default_check_type',
        readonly=False,
        string='Tipo de cheque por defecto',
    )
