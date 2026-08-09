import { Component, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { Dialog } from "@web/core/dialog/dialog";

export class CheckPaymentPopup extends Component {
    static template = "l10n_latam_check_ext.CheckPaymentPopup";
    static components = { Dialog };
    static props = {
        title: { type: String, optional: true },
        line: Object,
        banks: Array,
        getPayload: Function,
        close: Function,
    };
    static defaultProps = {
        title: _t("Datos del Cheque"),
    };

    setup() {
        const line = this.props.line;
        this.state = useState({
            number: line.l10n_latam_check_number || "",
            bank_id: line.l10n_latam_check_bank_id?.id || false,
            issuer_vat: line.l10n_latam_check_issuer_vat || "",
            check_type: line.l10n_latam_check_type || "common",
            issue_date: this._toIso(line.l10n_latam_check_issue_date) || this._today(),
            payment_date: this._toIso(line.l10n_latam_check_payment_date) || this._today(),
        });
    }

    _today() {
        return new Date().toISOString().split("T")[0];
    }

    _toIso(dateTime) {
        return dateTime ? dateTime.toISODate() : false;
    }

    get amount() {
        return this.props.line.getAmount();
    }

    get isValid() {
        return Boolean(
            this.state.number && this.state.bank_id && this.state.issue_date && this.state.payment_date
        );
    }

    confirm() {
        if (!this.isValid) {
            return;
        }
        this.props.getPayload({ ...this.state });
        this.props.close();
    }

    discard() {
        this.props.close();
    }
}
