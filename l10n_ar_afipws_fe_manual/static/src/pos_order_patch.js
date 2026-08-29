import { patch } from "@web/core/utils/patch";
import { PosOrder } from "@point_of_sale/app/models/pos_order";

// Core forces `to_invoice = true` whenever a "company" partner is picked
// (point_of_sale's own pos_order.js setPartner():
// `if (partner.is_company) this.setToInvoice(true)`), no matter where the
// selection happens. `payment_screen_patch.js`'s onMounted() only reverts
// this when the partner was already set *before* entering the Payment
// screen (e.g. from the cart) -- picking/changing the customer directly
// from within the Payment screen calls setPartner() *after* that revert
// already ran once, so it sticks. Undo it at the source instead, so it's
// covered regardless of when/where the partner gets picked.
patch(PosOrder.prototype, {
    setPartner(partner) {
        super.setPartner(...arguments);
        if (this.isArgentineanCompany()) {
            this.setToInvoice(false);
        }
    },
});
