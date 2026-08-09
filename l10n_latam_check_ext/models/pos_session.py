from odoo import api, models


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _load_pos_data_models(self, config):
        models_to_load = super()._load_pos_data_models(config)
        has_check_payment_method = config.payment_method_ids.filtered(
            lambda pm: pm.payment_method_type == "check"
        )
        if has_check_payment_method:
            models_to_load = models_to_load + ["res.bank"]
        return models_to_load
