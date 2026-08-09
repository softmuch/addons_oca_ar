import { patch } from "@web/core/utils/patch";
import { PosStore } from "@point_of_sale/app/services/pos_store";
import { makeAwaitable } from "@point_of_sale/app/utils/make_awaitable_dialog";
import { CheckPaymentPopup } from "@l10n_latam_check_ext/app/components/check_payment_popup/check_payment_popup";

const { DateTime } = luxon;

patch(PosStore.prototype, {
    async openCheckPaymentPopup(line) {
        if (line.payment_method_id.payment_method_type !== "check") {
            return false;
        }
        const banks = this.models["res.bank"] ? this.models["res.bank"].getAll() : [];
        const payload = await makeAwaitable(this.dialog, CheckPaymentPopup, { line, banks });
        if (!payload) {
            return false;
        }
        line.setAmount(payload.amount);
        line.l10n_latam_check_number = payload.number;
        line.l10n_latam_check_bank_id = payload.bank_id
            ? this.models["res.bank"].get(payload.bank_id)
            : false;
        line.l10n_latam_check_issuer_vat = payload.issuer_vat;
        line.l10n_latam_check_type = payload.check_type;
        line.l10n_latam_check_issue_date = payload.issue_date
            ? DateTime.fromISO(payload.issue_date)
            : false;
        line.l10n_latam_check_payment_date = payload.payment_date
            ? DateTime.fromISO(payload.payment_date)
            : false;
        return true;
    },
});
