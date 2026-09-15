from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from .broker import AccountSnapshot
from .models import OrderIntent, PriceQuote, RiskLimits, canonical_symbol, finite


class RiskRejection(RuntimeError):
    pass


class RiskGate:
    def __init__(self, limits: RiskLimits):
        self.limits = limits

    def validate(self, intent: OrderIntent, account: AccountSnapshot, *, now: datetime | None = None) -> None:
        try:
            account.validate()
            finite(intent.quantity, "quantity", positive=True)
            finite(intent.reference_price, "reference_price", positive=True)
            finite(intent.limit_price, "limit_price", positive=True)
            if intent.price_as_of is None:
                raise ValueError("a timestamped execution quote is required")
            PriceQuote(intent.reference_price, intent.price_as_of).validate(self.limits, now)
            if canonical_symbol(intent.symbol) != intent.symbol:
                raise ValueError("symbol must be canonical")
            if not intent.client_order_id or len(intent.client_order_id) > 48:
                raise ValueError("invalid client order ID")
        except (ValueError, TypeError) as exc:
            raise RiskRejection(str(exc)) from exc
        if intent.side not in {"buy", "sell"}:
            raise RiskRejection(f"unsupported side: {intent.side}")
        slip = self.limits.max_slippage_bps / Decimal("10000")
        if not intent.reference_price * (1 - slip) <= intent.limit_price <= intent.reference_price * (1 + slip):
            raise RiskRejection("limit price exceeds slippage policy")
        if intent.notional > self.limits.max_order_notional:
            raise RiskRejection("order exceeds max_order_notional")
        if account.open_orders >= self.limits.max_open_orders:
            raise RiskRejection("too many open orders")
        symbol = intent.symbol
        if intent.side == "sell":
            if account.pending_buy_notionals.get(symbol, Decimal("0")):
                raise RiskRejection("reconcile pending buys before reducing this position")
            if intent.quantity > account.available_to_sell(symbol):
                raise RiskRejection("sell would create a short position or oversell reserved shares")
            # A valid long-only reduction remains allowed when market moves exceed caps.
            return
        if account.pending_sell_quantities.get(symbol, Decimal("0")):
            raise RiskRejection("reconcile pending sells before increasing this position")
        reserved = sum(account.pending_buy_notionals.values(), Decimal("0"))
        if intent.notional > max(Decimal("0"), account.cash - reserved):
            raise RiskRejection("insufficient available cash after pending orders")
        resulting_symbol = (account.symbol_notionals.get(symbol, Decimal("0"))
                            + account.pending_buy_notionals.get(symbol, Decimal("0")) + intent.notional)
        if resulting_symbol > self.limits.max_symbol_notional:
            raise RiskRejection("symbol exposure exceeds max_symbol_notional")
        if account.gross_notional + reserved + intent.notional > self.limits.max_gross_notional:
            raise RiskRejection("gross exposure exceeds max_gross_notional")
