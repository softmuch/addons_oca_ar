import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";

// l10n_ar_pos forces setToInvoice(true) on every Argentine company order.
// This patch reverts that so the invoice button is off by default.
patch(PaymentScreen.prototype, {
    onMounted() {
        super.onMounted();
        if (this.pos.isArgentineanCompany()) {
            this.currentOrder.setToInvoice(false);
        }
    },
});
