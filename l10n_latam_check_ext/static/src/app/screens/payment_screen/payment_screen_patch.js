import { patch } from "@web/core/utils/patch";
import { _t } from "@web/core/l10n/translation";
import { AlertDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
        if (paymentMethod.payment_method_type === "check" && !this._hasRealPartnerForCheck()) {
            this.dialog.add(AlertDialog, {
                title: _t("Cliente requerido"),
                body: _t(
                    'Elegí un cliente distinto de "Consumidor Final Anónimo" antes de pagar con cheque.'
                ),
            });
            return false;
        }
        const result = await super.addNewPaymentLine(...arguments);
        if (result && paymentMethod.payment_method_type === "check") {
            const line = this.paymentLines.at(-1);
            const confirmed = await this.pos.openCheckPaymentPopup(line);
            if (!confirmed) {
                this.deletePaymentLine(line.uuid);
            }
        }
        return result;
    },

    // `pos.config._consumidor_final_anonimo_id` is loaded into the frontend
    // by `l10n_ar_pos/models/pos_config.py` (AR companies only). Falls back
    // to just requiring *some* partner if that id isn't available (module
    // not installed, or non-AR company).
    _hasRealPartnerForCheck() {
        const partner = this.currentOrder.partner_id;
        if (!partner) {
            return false;
        }
        const anonymousId = this.pos.config._consumidor_final_anonimo_id;
        return !anonymousId || partner.id !== anonymousId;
    },
});
