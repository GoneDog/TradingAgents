from __future__ import annotations

from .broker import BrokerAdapter, OrderReceipt
from .ledger import IntentConflict, Ledger, ReconciliationRequired
from .models import OrderIntent
from .risk import RiskGate, RiskRejection


class Operator:
    def __init__(self, broker: BrokerAdapter, risk: RiskGate, ledger: Ledger):
        self.broker = broker
        self.risk = risk
        self.ledger = ledger

    def preflight(self, pending_id: str | None = None):
        """Call under ledger.exclusive; reconcile before sizing or risk validation."""
        account = self.broker.snapshot()
        account.validate()
        self.ledger.bind_account(account.account_id)
        for row in self.ledger.active_orders():
            client_id = row["client_order_id"]
            if row["status"] == "pending":
                if client_id != pending_id:
                    raise ReconciliationRequired("a saved, unsubmitted intent needs recovery first")
                continue
            receipt = self.broker.lookup(client_id)
            if receipt is None:
                # Even a 404 is insufficient proof after an attempted POST.
                raise ReconciliationRequired("submission unresolved; refusing automatic resubmission")
            if receipt.client_order_id != client_id:
                raise ReconciliationRequired("broker lookup returned a different client order ID")
            self.ledger.record_receipt(receipt)
        account = self.broker.snapshot()
        account.validate()
        self.ledger.bind_account(account.account_id)
        for row in self.ledger.active_orders():
            if row["status"] != "pending" and row["client_order_id"] not in account.open_order_ids:
                raise ReconciliationRequired("broker order state changed during reconciliation; retry lookup, not submission")
        return account

    def execute(self, intent: OrderIntent) -> OrderReceipt | None:
        with self.ledger.exclusive():
            saved = self.ledger.get_intent(intent.client_order_id)
            if saved is not None and saved != intent:
                raise IntentConflict("retry must use the original persisted intent")
            account = self.preflight(intent.client_order_id)
            row = self.ledger.get_order(intent.client_order_id)
            if row and row["status"] != "pending":
                return None
            # Recover orphaned broker orders even if this ledger has no row.
            existing = self.broker.lookup(intent.client_order_id)
            if existing is not None:
                if saved is None:
                    raise ReconciliationRequired("broker has an order missing from this ledger")
                if existing.client_order_id != intent.client_order_id:
                    raise ReconciliationRequired("broker lookup returned a different client order ID")
                self.ledger.record_receipt(existing)
                return None
            try:
                self.risk.validate(intent, account)
            except RiskRejection:
                if row:
                    self.ledger.set_status(intent.client_order_id, "rejected")
                raise
            self.ledger.record_pending(intent)
            # Commit BEFORE POST; after this point any failure is ambiguous.
            self.ledger.set_status(intent.client_order_id, "submitting")
            try:
                receipt = self.broker.submit(intent)
                if receipt.client_order_id != intent.client_order_id:
                    raise ReconciliationRequired("broker receipt has a different client order ID")
                self.ledger.record_receipt(receipt)
                return receipt
            except Exception as exc:
                self.ledger.set_status(intent.client_order_id, "unknown")
                raise ReconciliationRequired("submission outcome unknown; broker reconciliation required") from exc
