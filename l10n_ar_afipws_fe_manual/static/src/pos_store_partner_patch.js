import { PosStore } from "@point_of_sale/app/store/pos_store";
import { patch } from "@web/core/utils/patch";

// AFIP requires a responsibility type on the customer to resolve which
// document type (Factura A/B/C) an invoice must use. A partner without one
// blocks invoicing ("el diario requiere un tipo de documento..."). Called
// from PaymentScreen.validateOrder right before finalizing, so it must be
// awaited and written directly (no queue) — the invoice is generated right
// after and needs the field already committed server-side.
patch(PosStore.prototype, {
    async ensureAfipResponsibilityType(partner) {
        if (
            !partner ||
            !this.isArgentineanCompany() ||
            partner.l10n_ar_afip_responsibility_type_id
        ) {
            return;
        }
        const consumidorFinal = this.models["l10n_ar.afip.responsibility.type"]
            .getAll()
            .find((type) => type.name === "Consumidor Final");
        if (!consumidorFinal) {
            return;
        }
        await this.data.orm.write("res.partner", [partner.id], {
            l10n_ar_afip_responsibility_type_id: consumidorFinal.id,
        });
        partner.update({ l10n_ar_afip_responsibility_type_id: consumidorFinal.id });
    },
});
