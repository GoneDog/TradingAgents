from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from .models import OrderIntent, PriceQuote, canonical_symbol, finite


@dataclass(frozen=True)
class AccountSnapshot:
    cash: Decimal
    gross_notional: Decimal
    open_orders: int
    symbol_notionals: dict[str, Decimal]
    symbol_quantities: dict[str, Decimal] = field(default_factory=dict)
    pending_buy_notionals: dict[str, Decimal] = field(default_factory=dict)
    pending_sell_quantities: dict[str, Decimal] = field(default_factory=dict)
    available_quantities: dict[str, Decimal] = field(default_factory=dict)
    open_order_ids: frozenset[str] = frozenset()
    account_id: str = "simulation"

    def validate(self) -> None:
        finite(self.cash, "cash")
        finite(self.gross_notional, "gross_notional")
        if isinstance(self.open_orders, bool) or not isinstance(self.open_orders, int) or self.open_orders < 0 or self.open_orders != len(self.open_order_ids):
            raise ValueError("open-order reconciliation is incomplete")
        for mapping in (self.symbol_notionals, self.symbol_quantities,
                        self.pending_buy_notionals, self.pending_sell_quantities,
                        self.available_quantities):
            for symbol, value in mapping.items():
                if canonical_symbol(symbol) != symbol:
                    raise ValueError("snapshot symbols must be canonical")
                finite(value, symbol)
        if set(self.symbol_notionals) != set(self.symbol_quantities):
            raise ValueError("position quantities are missing")
        if self.gross_notional < sum(self.symbol_notionals.values(), Decimal("0")):
            raise ValueError("gross exposure is inconsistent")
        if any(not isinstance(key, str) or not key for key in self.open_order_ids):
            raise ValueError("open-order identity is incomplete")
        if not self.account_id:
            raise ValueError("account identity is missing")

    def available_to_sell(self, symbol: str) -> Decimal:
        held = self.symbol_quantities.get(symbol, Decimal("0"))
        unreserved = max(Decimal("0"), held - self.pending_sell_quantities.get(symbol, Decimal("0")))
        # Broker qty_available already subtracts reservations; do not subtract twice.
        return min(unreserved, self.available_quantities.get(symbol, held))


@dataclass(frozen=True)
class OrderReceipt:
    client_order_id: str
    broker_order_id: str
    status: str


class BrokerAdapter(Protocol):
    def snapshot(self) -> AccountSnapshot: ...
    def submit(self, intent: OrderIntent) -> OrderReceipt: ...
    def lookup(self, client_order_id: str) -> OrderReceipt | None: ...
    def quote(self, symbol: str) -> PriceQuote: ...


class DryRunBroker:
    """In-memory, unfilled limit orders; not a fill simulator or persistent broker."""

    def __init__(self, cash: Decimal = Decimal("10000")):
        self._cash = cash
        self._orders: dict[str, OrderReceipt] = {}
        self._intents: dict[str, OrderIntent] = {}

    def snapshot(self) -> AccountSnapshot:
        pending: dict[str, Decimal] = {}
        for intent in self._intents.values():
            if intent.side == "buy":
                pending[intent.symbol] = pending.get(intent.symbol, Decimal("0")) + intent.notional
        return AccountSnapshot(
            cash=self._cash, gross_notional=Decimal("0"),
            open_orders=len(self._orders), symbol_notionals={},
            pending_buy_notionals=pending,
            open_order_ids=frozenset(self._orders), account_id="dry-run",
        )

    def submit(self, intent: OrderIntent) -> OrderReceipt:
        existing = self._orders.get(intent.client_order_id)
        if existing is not None:
            if self._intents[intent.client_order_id] != intent:
                raise ValueError("client order ID already belongs to a different intent")
            return existing
        receipt = OrderReceipt(intent.client_order_id, f"dry-{len(self._orders) + 1}", "accepted")
        self._orders[intent.client_order_id] = receipt
        self._intents[intent.client_order_id] = intent
        return receipt

    def lookup(self, client_order_id: str) -> OrderReceipt | None:
        return self._orders.get(client_order_id)

    def quote(self, symbol: str) -> PriceQuote:
        raise RuntimeError("DryRunBroker requires an explicitly injected test quote")
