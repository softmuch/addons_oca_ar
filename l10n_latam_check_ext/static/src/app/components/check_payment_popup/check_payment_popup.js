import { Component, useState } from "@odoo/owl";
import { _t } from "@web/core/l10n/translation";
import { Dialog } from "@web/core/dialog/dialog";
import { AutoComplete } from "@web/core/autocomplete/autocomplete";
import { formatFloat } from "@web/core/utils/numbers";
import { parseFloat } from "@web/views/fields/parsers";

// Same algorithm as Python's stdnum.ar.cuit, used by l10n_latam.check's own
// `_check_issuer_vat` constraint - validated here too so a bad CUIT is caught
// in the popup instead of blowing up the whole session-close at the end.
const CUIT_TYPES = ["20", "23", "24", "27", "30", "33", "34", "50", "51", "55"];

function cuitCheckDigit(number10) {
    const weights = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2];
    let check = 0;
    for (let i = 0; i < 10; i++) {
        check += weights[i] * parseInt(number10[i], 10);
    }
    check = check % 11;
    return "012345678990"[11 - check];
}

function isValidCuit(raw) {
    const number = (raw || "").replace(/[\s-]/g, "");
    if (!/^\d{11}$/.test(number)) {
        return false;
    }
    if (!CUIT_TYPES.includes(number.slice(0, 2))) {
        return false;
    }
    return cuitCheckDigit(number.slice(0, 10)) === number[10];
}

export class CheckPaymentPopup extends Component {
    static template = "l10n_latam_check_ext.CheckPaymentPopup";
    static components = { Dialog, AutoComplete };
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
            amountText: formatFloat(line.getAmount()),
            number: line.l10n_latam_check_number || "",
            bank_id: line.l10n_latam_check_bank_id?.id || false,
            bank_name: line.l10n_latam_check_bank_id?.name || "",
            issuer_vat: line.l10n_latam_check_issuer_vat || "",
            check_type: line.l10n_latam_check_type || "common",
            issue_date: this._toIso(line.l10n_latam_check_issue_date) || this._today(),
            payment_date: this._toIso(line.l10n_latam_check_payment_date) || this._today(),
        });
    }

    getBankSources() {
        return [
            {
                options: (currentInput) => {
                    const query = currentInput.trim().toLowerCase();
                    const banks = query
                        ? this.props.banks.filter((bank) => bank.name.toLowerCase().includes(query))
                        : this.props.banks;
                    return banks.slice(0, 30).map((bank) => ({
                        label: bank.name,
                        onSelect: () => this.selectBank(bank),
                    }));
                },
            },
        ];
    }

    selectBank(bank) {
        this.state.bank_id = bank.id;
        this.state.bank_name = bank.name;
    }

    onBankInput({ inputValue }) {
        if (!inputValue) {
            this.state.bank_id = false;
        }
    }

    _today() {
        return new Date().toISOString().split("T")[0];
    }

    _toIso(dateTime) {
        return dateTime ? dateTime.toISODate() : false;
    }

    get amount() {
        try {
            return parseFloat(this.state.amountText);
        } catch {
            return 0;
        }
    }

    formatAmountOnBlur() {
        this.state.amountText = formatFloat(this.amount);
    }

    get issuerVatError() {
        if (this.state.issuer_vat && !isValidCuit(this.state.issuer_vat)) {
            return _t("CUIT inválido. Formato esperado: 20055361682");
        }
        return false;
    }

    get isValid() {
        return Boolean(
            this.amount > 0 &&
                this.state.number &&
                this.state.bank_id &&
                this.state.issue_date &&
                this.state.payment_date &&
                !this.issuerVatError
        );
    }

    confirm() {
        if (!this.isValid) {
            return;
        }
        this.props.getPayload({ ...this.state, amount: this.amount });
        this.props.close();
    }

    discard() {
        this.props.close();
    }
}
