from odoo import _, fields, models
from odoo.exceptions import UserError


class ValidateAccountMove(models.TransientModel):
    _inherit = "validate.account.move"

    async_post = fields.Boolean(
        "Asynchronous Post", default=False, help="Post moves asynchronously."
    )

    def validate_move(self):
        if self.async_post:
            moves = self.move_ids.filtered("line_ids")
            if not moves:
                raise UserError(
                    _("There are no journal items in the draft state to post.")
                )
            moves.asynchronous_post = True
            return {"type": "ir.actions.act_window_close"}
        else:
            return super().validate_move()
