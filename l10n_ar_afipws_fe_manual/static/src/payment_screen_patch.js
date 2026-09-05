import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";

// l10n_ar_pos forces set_to_invoice(true) on every Argentine company order.
// This patch reverts that so the invoice button is off by default.
patch(PaymentScreen.prototype, {
    onMounted() {
        super.onMounted();
        if (this.pos.isArgentineanCompany()) {
            this.currentOrder.set_to_invoice(false);
        }
    },
    async validateOrder(isForceValidate) {
        if (this.pos.isArgentineanCompany() && this.currentOrder.is_to_invoice()) {
            await this.pos.ensureAfipResponsibilityType(this.currentOrder.get_partner());
        }
        return super.validateOrder(...arguments);
    },
});
