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
            return None

        account = self.broker.snapshot()
        self.risk.validate(intent, account)

        # Persist identity before submission. If the process dies after the broker
        # accepts the order, a restart will not blindly submit the same intent again.
        self.ledger.record_pending(intent)
        receipt = self.broker.submit(intent)
        self.ledger.record_receipt(receipt)
        return receipt
