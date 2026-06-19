from odoo import models, fields


class L10nLatamCheckExt(models.Model):
    _inherit = 'l10n_latam.check'

    check_type = fields.Selection(
        selection=[
            ('common', 'Cheque Común'),
            ('deferred', 'Cheque de Pago Diferido (CPD)'),
        ],
        string='Tipo de Cheque',
        help=(
            "Cheque Común: El más utilizado. Se hace efectivo al momento de presentarlo en el banco "
            "(aunque en la práctica suele usarse con fecha futura, lo que técnicamente es un "
            "\"cheque diferido informal\" o \"cheque de pago a la vista postdatado\"). "
            "Vigencia: 30 días corridos desde la fecha de emisión.\n\n"
            "Cheque de Pago Diferido (CPD): Tiene una fecha de pago futura indicada explícitamente, "
            "que puede ir de 1 hasta 360 días desde la emisión. Es muy usado en Argentina como "
            "instrumento de financiamiento, ya que puede negociarse (descontarse) en el mercado de "
            "capitales antes de su vencimiento, incluso a través del sistema de cheques electrónicos "
            "(eCheq) en mercados como el MAE o Bolsas y Mercados Argentinos (BYMA)."
        ),
    )

    issue_date = fields.Date(
        string='Fecha de Emisión',
        help=(
            "Fecha en que se emitió el cheque. "
            "Para cheques comunes determina el inicio de la vigencia de 30 días corridos. "
            "Para cheques de pago diferido (CPD) es el punto de partida desde el cual se cuenta "
            "el plazo de pago diferido (entre 1 y 360 días)."
        ),
    )
