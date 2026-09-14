from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from .models import OrderIntent


@dataclass(frozen=True)
class AccountSnapshot:
    cash: Decimal
    gross_notional: Decimal
    open_orders: int
    symbol_notionals: dict[str, Decimal]


@dataclass(frozen=True)
class OrderReceipt:
    client_order_id: str
    broker_order_id: str
    status: str


class BrokerAdapter(Protocol):
    def snapshot(self) -> AccountSnapshot: ...

    def submit(self, intent: OrderIntent) -> OrderReceipt: ...

    def lookup(self, client_order_id: str) -> OrderReceipt | None: ...


class DryRunBroker:
    """In-memory execution adapter for integration tests and unattended dry runs."""

    def __init__(self, cash: Decimal = Decimal("10000")):
        self._cash = cash
        self._orders: dict[str, OrderReceipt] = {}

    def snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(
            cash=self._cash,
            gross_notional=Decimal("0"),
            open_orders=0,
            symbol_notionals={},
        )

    def submit(self, intent: OrderIntent) -> OrderReceipt:
        existing = self._orders.get(intent.client_order_id)
        if existing is not None:
            return existing
        receipt = OrderReceipt(
            client_order_id=intent.client_order_id,
            broker_order_id=f"dry-{len(self._orders) + 1}",
            status="accepted",
        )
        self._orders[intent.client_order_id] = receipt
        return receipt

    def lookup(self, client_order_id: str) -> OrderReceipt | None:
        return self._orders.get(client_order_id)
