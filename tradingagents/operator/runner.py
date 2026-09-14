from __future__ import annotations

from .broker import BrokerAdapter, OrderReceipt
from .ledger import Ledger
from .models import OrderIntent
from .risk import RiskGate


class Operator:
    """Deterministic bridge between an AI-produced order intent and a broker adapter."""

    def __init__(self, broker: BrokerAdapter, risk: RiskGate, ledger: Ledger):
        self.broker = broker
        self.risk = risk
        self.ledger = ledger

    def execute(self, intent: OrderIntent) -> OrderReceipt | None:
        if self.ledger.has_order(intent.client_order_id):
            # A previous process may have died after persisting the intent but
            # before recording the broker response. Reconcile using the same
            # client order ID. If the broker has it, do not submit again.
            existing = self.broker.lookup(intent.client_order_id)
            if existing is not None:
                self.ledger.record_receipt(existing)
                return None
            # A definitive not-found means the persisted pending intent never
            # reached the broker. Retrying with the same stable client ID keeps
            # the broker-side request idempotent.

        account = self.broker.snapshot()
        self.risk.validate(intent, account)

        self.ledger.record_pending(intent)
        receipt = self.broker.submit(intent)
        self.ledger.record_receipt(receipt)
        return receipt
