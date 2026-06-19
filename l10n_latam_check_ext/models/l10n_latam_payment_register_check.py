from odoo import models, fields


class L10nLatamPaymentRegisterCheckExt(models.TransientModel):
    _inherit = 'l10n_latam.payment.register.check'

    check_type = fields.Selection(
        selection=[
            ('common', 'Cheque Común'),
            ('deferred', 'Cheque de Pago Diferido (CPD)'),
        ],
        string='Tipo de Cheque',
    )
    issue_date = fields.Date(string='Fecha de Emisión')