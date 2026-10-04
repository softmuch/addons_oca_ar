import { PaymentScreen } from "@point_of_sale/app/screens/payment_screen/payment_screen";
import { patch } from "@web/core/utils/patch";

// l10n_ar_pos forces set_to_invoice(true) on every Argentine company order.
// This patch replaces that with the company setting "Factura activada por
// defecto en POS" (l10n_ar_pos_invoice_default, off by default).
patch(PaymentScreen.prototype, {
    onMounted() {
        super.onMounted();
        if (this.pos.isArgentineanCompany()) {
            this.currentOrder.set_to_invoice(Boolean(this.pos.company.l10n_ar_pos_invoice_default));
        }
    },

    // Core always downloads the invoice PDF after validating an invoiced order.
    // Follow the company setting "Descargar PDF de factura en POS"
    // (l10n_ar_pos_invoice_download, off by default) instead.
    shouldDownloadInvoice() {
        if (this.pos.isArgentineanCompany()) {
            return Boolean(this.pos.company.l10n_ar_pos_invoice_download);
        }
        return super.shouldDownloadInvoice();
    },
});
