import { patch } from "@web/core/utils/patch";
import { PaymentScreenPaymentLines } from "@point_of_sale/app/screens/payment_screen/payment_lines/payment_lines";

patch(PaymentScreenPaymentLines.prototype, {
    isCheckPayment(line) {
        return line.payment_method_id?.payment_method_type === "check";
    },

    async editCheckPayment(line) {
        await this.pos.openCheckPaymentPopup(line);
    },
});
