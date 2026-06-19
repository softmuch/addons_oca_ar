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
