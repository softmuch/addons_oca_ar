from odoo import models, Command


class AccountPaymentRegisterExt(models.TransientModel):
    _inherit = 'account.payment.register'

    def _create_payment_vals_from_wizard(self, batch_result):
        vals = super()._create_payment_vals_from_wizard(batch_result)
        if self.l10n_latam_new_check_ids and 'l10n_latam_new_check_ids' in vals:
            vals['l10n_latam_new_check_ids'] = [
                Command.create({
                    'name': x.name,
                    'bank_id': x.bank_id.id,
                    'issuer_vat': x.issuer_vat,
                    'payment_date': x.payment_date,
                    'amount': x.amount,
                    'check_type': x.check_type,
                    'issue_date': x.issue_date,
                }) for x in self.l10n_latam_new_check_ids
            ]
        return vals