from odoo import fields, models


class PosPayment(models.Model):
    _inherit = "pos.payment"

    l10n_latam_check_number = fields.Char(string="Número de Cheque")
    l10n_latam_check_bank_id = fields.Many2one("res.bank", string="Banco Emisor")
    l10n_latam_check_issuer_vat = fields.Char(string="CUIT Emisor")
    l10n_latam_check_type = fields.Selection(
        selection=[
            ("common", "Cheque Común"),
            ("deferred", "Cheque de Pago Diferido (CPD)"),
        ],
        string="Tipo de Cheque",
    )
    l10n_latam_check_issue_date = fields.Date(string="Fecha de Emisión")
    l10n_latam_check_payment_date = fields.Date(string="Fecha de Cobro")
