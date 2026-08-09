from odoo import _, api, models, Command


class PosSession(models.Model):
    _inherit = "pos.session"

    @api.model
    def _load_pos_data_models(self, config):
        models_to_load = super()._load_pos_data_models(config)
        has_check_payment_method = config.payment_method_ids.filtered(
            lambda pm: pm.payment_method_type == "check"
        )
        if has_check_payment_method:
            models_to_load = models_to_load + ["res.bank"]
        return models_to_load

    def _get_l10n_latam_check_vals(self, payment):
        return Command.create({
            "name": payment.l10n_latam_check_number,
            "bank_id": payment.l10n_latam_check_bank_id.id,
            "issuer_vat": payment.l10n_latam_check_issuer_vat,
            "check_type": payment.l10n_latam_check_type,
            "issue_date": payment.l10n_latam_check_issue_date,
            "payment_date": payment.l10n_latam_check_payment_date,
            "amount": payment.amount,
        })

    def _link_l10n_latam_checks(self, account_payment, payments):
        for payment, check in zip(payments, account_payment.l10n_latam_new_check_ids):
            payment.l10n_latam_check_id = check.id

    # The check-in-hand journal is normally type=cash (per l10n_latam_check's
    # own `_get_payment_method_information`, code 'new_third_party_checks' is
    # meant for cash-type journals). POS routes cash-type payments through
    # bank statement lines, not account.payment, so l10n_latam.check (which
    # requires a payment_id) could never be created. We pull check-type
    # payments out of the cash bucket here and process them like bank
    # payments instead, without touching the journal's type.
    def _create_bank_payment_moves(self, data):
        combine_receivables_cash = data.get('combine_receivables_cash') or {}
        split_receivables_cash = data.get('split_receivables_cash') or {}
        check_combine = {pm: a for pm, a in combine_receivables_cash.items() if pm.payment_method_type == "check"}
        check_split = {p: a for p, a in split_receivables_cash.items() if p.payment_method_id.payment_method_type == "check"}

        data = super()._create_bank_payment_moves(data)
        if not check_combine and not check_split:
            return data

        MoveLine = data.get('MoveLine')
        bank_payment_method_diffs = data.get('bank_payment_method_diffs') or {}
        payment_method_to_receivable_lines = data.get('payment_method_to_receivable_lines') or {}
        payment_to_receivable_lines = data.get('payment_to_receivable_lines') or {}

        for payment_method, amounts in check_combine.items():
            combine_receivable_line = MoveLine.create(self._get_combine_receivable_vals(payment_method, amounts['amount'], amounts['amount_converted']))
            payment_receivable_line = self._create_combine_account_payment(payment_method, amounts, diff_amount=bank_payment_method_diffs.get(payment_method.id) or 0)
            payment_method_to_receivable_lines[payment_method] = combine_receivable_line | payment_receivable_line

        for payment, amounts in check_split.items():
            split_receivable_line = MoveLine.create(self._get_split_receivable_vals(payment, amounts['amount'], amounts['amount_converted']))
            payment_receivable_line = self._create_split_account_payment(payment, amounts)
            payment_to_receivable_lines[payment] = split_receivable_line | payment_receivable_line

        data['payment_method_to_receivable_lines'] = payment_method_to_receivable_lines
        data['payment_to_receivable_lines'] = payment_to_receivable_lines
        return data

    def _create_cash_statement_lines_and_cash_move_lines(self, data):
        combine_receivables_cash = data.get('combine_receivables_cash') or {}
        split_receivables_cash = data.get('split_receivables_cash') or {}
        has_checks = any(pm.payment_method_type == "check" for pm in combine_receivables_cash) or \
            any(p.payment_method_id.payment_method_type == "check" for p in split_receivables_cash)
        if has_checks:
            data = dict(data)
            data['combine_receivables_cash'] = {pm: a for pm, a in combine_receivables_cash.items() if pm.payment_method_type != "check"}
            data['split_receivables_cash'] = {p: a for p, a in split_receivables_cash.items() if p.payment_method_id.payment_method_type != "check"}
        return super()._create_cash_statement_lines_and_cash_move_lines(data)

    # Full override (not super()) needed: the checks must exist on
    # `l10n_latam_new_check_ids` *before* `action_post()` runs, otherwise
    # l10n_latam_check's own payment-amount-vs-checks-amount validation
    # (which runs during post, when the recordset is still empty) blocks it.
    def _create_combine_account_payment(self, payment_method, amounts, diff_amount):
        if payment_method.payment_method_type != "check":
            return super()._create_combine_account_payment(payment_method, amounts, diff_amount)

        outstanding_account = payment_method.outstanding_account_id
        destination_account = self._get_receivable_account(payment_method)
        payment_type = "inbound"
        if self.currency_id.compare_amounts(amounts['amount'], 0) < 0:
            payment_type = 'outbound'

        checks = self.env['pos.payment'].search([
            ('session_id', '=', self.id),
            ('payment_method_id', '=', payment_method.id),
            ('l10n_latam_check_number', '!=', False),
        ])

        account_payment = self.env['account.payment'].with_context(pos_payment=True).create({
            'amount': abs(amounts['amount']),
            'journal_id': payment_method.journal_id.id,
            'force_outstanding_account_id': outstanding_account.id,
            'destination_account_id': destination_account.id,
            'memo': _('Combine %(payment_method)s POS payments from %(session)s', payment_method=payment_method.name, session=self.name),
            'pos_payment_method_id': payment_method.id,
            'pos_session_id': self.id,
            'company_id': self.company_id.id,
            'payment_type': payment_type,
            'l10n_latam_new_check_ids': [self._get_l10n_latam_check_vals(p) for p in checks],
        })
        self._link_l10n_latam_checks(account_payment, checks)

        self._ensure_payment_outstanding_account(account_payment, amounts['amount'])
        account_payment.action_post()

        diff_amount_compare_to_zero = self.currency_id.compare_amounts(diff_amount, 0)
        if diff_amount_compare_to_zero != 0:
            self._apply_diff_on_account_payment_move(account_payment, payment_method, diff_amount)

        return account_payment.move_id.line_ids.filtered(lambda line: line.account_id == self._get_receivable_account(payment_method))

    def _create_split_account_payment(self, payment, amounts):
        if payment.payment_method_id.payment_method_type != "check":
            return super()._create_split_account_payment(payment, amounts)

        payment_method = payment.payment_method_id
        if not payment_method.journal_id:
            return self.env['account.move.line']
        outstanding_account = payment_method.outstanding_account_id
        accounting_partner = self.env["res.partner"]._find_accounting_partner(payment.partner_id)
        destination_account = accounting_partner.property_account_receivable_id
        payment_type = "inbound"
        if self.currency_id.compare_amounts(amounts['amount'], 0) < 0:
            payment_type = 'outbound'

        account_payment = self.env['account.payment'].create({
            'amount': abs(amounts['amount']),
            'partner_id': accounting_partner.id,
            'journal_id': payment_method.journal_id.id,
            'force_outstanding_account_id': outstanding_account.id,
            'destination_account_id': destination_account.id,
            'memo': _('%(payment_method)s POS payment of %(partner)s in %(session)s', payment_method=payment_method.name, partner=payment.partner_id.display_name, session=self.name),
            'pos_payment_method_id': payment_method.id,
            'pos_session_id': self.id,
            'payment_type': payment_type,
            'l10n_latam_new_check_ids': [self._get_l10n_latam_check_vals(payment)] if payment.l10n_latam_check_number else [],
        })
        self._link_l10n_latam_checks(account_payment, payment)

        self._ensure_payment_outstanding_account(account_payment, amounts['amount'])
        account_payment.action_post()
        return account_payment.move_id.line_ids.filtered(lambda line: line.account_id == accounting_partner.property_account_receivable_id)
