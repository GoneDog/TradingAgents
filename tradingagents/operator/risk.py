from __future__ import annotations

from decimal import Decimal

from .broker import AccountSnapshot
from .models import OrderIntent, RiskLimits


class RiskRejection(RuntimeError):
    pass


class RiskGate:
    def __init__(self, limits: RiskLimits):
        self.limits = limits

    def validate(self, intent: OrderIntent, account: AccountSnapshot) -> None:
        side = intent.side.lower()
        if side not in {"buy", "sell"}:
            raise RiskRejection(f"unsupported side: {intent.side}")
        if intent.quantity <= 0 or intent.reference_price <= 0:
            raise RiskRejection("quantity and reference price must be positive")
        if intent.notional > self.limits.max_order_notional:
            raise RiskRejection("order exceeds max_order_notional")
        if account.open_orders >= self.limits.max_open_orders:
            raise RiskRejection("too many open orders")

        current_symbol = account.symbol_notionals.get(intent.symbol, Decimal("0"))
        if side == "buy":
            resulting_symbol = current_symbol + intent.notional
            resulting_gross = account.gross_notional + intent.notional
            if intent.notional > account.cash:
                raise RiskRejection("insufficient available cash")
        else:
            if current_symbol < intent.notional and not self.limits.allow_shorting:
                raise RiskRejection("sell would create a short position")
            resulting_symbol = abs(current_symbol - intent.notional)
            resulting_gross = max(Decimal("0"), account.gross_notional - intent.notional)

        if resulting_symbol > self.limits.max_symbol_notional:
            raise RiskRejection("symbol exposure exceeds max_symbol_notional")
        if resulting_gross > self.limits.max_gross_notional:
            raise RiskRejection("gross exposure exceeds max_gross_notional")
