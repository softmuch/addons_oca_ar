from odoo import models, fields


class ResCompany(models.Model):
    _inherit = 'res.company'

    l10n_latam_own_check_alert_days = fields.Integer(
        string='Días de aviso antes del vencimiento',
        default=5,
    )
    l10n_latam_own_check_alert_user_ids = fields.Many2many(
        comodel_name='res.users',
        relation='l10n_latam_own_check_alert_company_user_rel',
        column1='company_id',
        column2='user_id',
        string='Usuarios a notificar',
    )
    l10n_latam_third_check_alert_days = fields.Integer(
        string='Días de aviso antes del vencimiento',
        default=5,
    )
    l10n_latam_third_check_alert_user_ids = fields.Many2many(
        comodel_name='res.users',
        relation='l10n_latam_third_check_alert_company_user_rel',
        column1='company_id',
        column2='user_id',
        string='Usuarios a notificar',
    )
