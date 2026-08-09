import { patch } from "@web/core/utils/patch";
import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";

patch(PaymentScreen.prototype, {
    async addNewPaymentLine(paymentMethod) {
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
});
