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

    # `state` is a stored compute (readonly=False): writing it directly is the
    # same pattern account.payment's own action_post() uses for asset_cash
    # outstanding accounts. A check received in the Invoicing app's payment
    # register wizard shows 'paid' immediately (no 'in_process' step) because
    # it gets reconciled straight against the invoice; a POS check never has
    # an invoice to reconcile against (it settles the session's own pos
    # receivable account instead), so `_compute_state` would otherwise leave
    # it at 'in_process' forever. Force it to match the Invoicing app.
    #
    # This must happen in `_reconcile_account_move_lines`, not right after
    # `action_post()`: that method (called later, outside `_create_account_move`)
    # reconciles the receivable-side line, which changes `move_id.line_ids.
    # amount_residual` - a dependency of `_compute_state` - re-triggering the
    # compute and undoing an earlier forced 'paid' every time.
    def _reconcile_account_move_lines(self, data):
        data = super()._reconcile_account_move_lines(data)
        self.env['account.payment'].search([
            ('pos_session_id', '=', self.id),
            ('pos_payment_method_id.payment_method_type', '=', 'check'),
        ]).write({'state': 'paid'})
        return data

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
    #
    # NOTE (odoxeus_rioseed): a check's `l10n_latam.check` record now gets
    # created instantly on `pos.payment` (create/write), regardless of
    # invoicing -- see odoxeus_rioseed's `pos_payment.py`. Here, at session
    # close, we only ever create the `account.payment` (and link it to that
    # already-existing check) for payments whose order was invoiced; a
    # check on a never-invoiced order intentionally never gets an
    # account.payment at all (confirmed with the client). Combining
    # multiple orders/customers into one `account.payment` -- which is what
    # `amounts`/`_get_receivable_account` below is built for -- doesn't make
    # sense once we need to reconcile against each order's own invoice, so
    # invoiced checks are processed one order at a time here regardless of
    # this payment method's `split_transactions` setting.
    def _create_combine_account_payment(self, payment_method, amounts, diff_amount):
        if payment_method.payment_method_type != "check":
            return super()._create_combine_account_payment(payment_method, amounts, diff_amount)

        invoiced_checks = self.env['pos.payment'].search([
            ('session_id', '=', self.id),
            ('payment_method_id', '=', payment_method.id),
            ('l10n_latam_check_number', '!=', False),
            ('account_move_id', '=', False),
            ('pos_order_id.account_move', '!=', False),
        ])
        result = self.env['account.move.line']
        for payment in invoiced_checks:
            result |= self._create_invoiced_check_account_payment(payment)
        return result

    def _create_invoiced_check_account_payment(self, payment):
        """Create the account.payment for one invoiced order's check
        payment, link it to the check already created instantly on the
        payment (odoxeus_rioseed), and reconcile it against that order's
        own invoice receivable line.
        """
        order = payment.pos_order_id
        payment_method = payment.payment_method_id
        accounting_partner = self.env["res.partner"]._find_accounting_partner(payment.partner_id)
        receivable_account = accounting_partner.with_company(order.company_id).property_account_receivable_id
        payment_type = "inbound"
        if self.currency_id.compare_amounts(payment.amount, 0) < 0:
            payment_type = 'outbound'

        account_payment = self.env['account.payment'].create({
            'amount': abs(payment.amount),
            'partner_id': accounting_partner.id,
            'journal_id': payment_method.journal_id.id,
            'force_outstanding_account_id': payment_method.outstanding_account_id.id,
            'destination_account_id': receivable_account.id,
            'memo': _('%(payment_method)s POS payment of %(partner)s in %(session)s',
                      payment_method=payment_method.name, partner=payment.partner_id.display_name, session=self.name),
            'pos_payment_method_id': payment_method.id,
            'pos_session_id': self.id,
            'payment_type': payment_type,
        })
        payment.l10n_latam_check_id.payment_id = account_payment.id
        payment.account_move_id = account_payment.move_id.id

        self._ensure_payment_outstanding_account(account_payment, payment.amount)
        account_payment.action_post()

        invoice_line = order.account_move.line_ids.filtered(
            lambda line: line.account_id == receivable_account and not line.reconciled
        )
        payment_line = account_payment.move_id.line_ids.filtered(
            lambda line: line.account_id == receivable_account and not line.reconciled
        )
        (invoice_line | payment_line).reconcile()
        return payment_line

    def _create_split_account_payment(self, payment, amounts):
        if payment.payment_method_id.payment_method_type != "check":
            return super()._create_split_account_payment(payment, amounts)

        if not payment.pos_order_id.account_move:
            # Never-invoiced order: this check intentionally never gets an
            # account.payment (confirmed with the client) -- the
            # l10n_latam.check already exists on its own, without a
            # payment_id, created instantly on the pos.payment.
            return self.env['account.move.line']

        return self._create_invoiced_check_account_payment(payment)
