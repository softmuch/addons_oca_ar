from odoo import models


class ResBank(models.Model):
    _inherit = ["res.bank", "pos.load.mixin"]

    def _load_pos_data_fields(self, config):
        return ["id", "name"]
