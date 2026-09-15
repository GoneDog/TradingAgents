from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from hashlib import sha256

from .broker import AccountSnapshot
from .models import Decision, OrderIntent, RiskLimits, canonical_symbol, finite


@dataclass(frozen=True)
class PositionTargets:
    buy: Decimal = Decimal("1.00")
    overweight: Decimal = Decimal("0.60")
    underweight: Decimal = Decimal("0.25")

    def __post_init__(self) -> None:
        for name in ("buy", "overweight", "underweight"):
            value = finite(getattr(self, name), name)
            if value > 1:
                raise ValueError(f"{name} target must be between 0 and 1")
        if not self.underweight <= self.overweight <= self.buy:
            raise ValueError("position targets must be ordered")


def order_id(decision_key: str, symbol: str) -> str:
    if not decision_key or len(decision_key) > 256:
        raise ValueError("an explicit, bounded decision key is required")
    # Rating, target, price and quantity are immutable payload, NOT retry identity.
    return "ta-" + sha256(f"{decision_key}|{canonical_symbol(symbol)}".encode()).hexdigest()[:32]


class DecisionPlanner:
    def __init__(self, limits: RiskLimits, targets: PositionTargets | None = None):
        self.limits = limits
        self.targets = targets or PositionTargets()

    def target_notional(self, decision: Decision) -> Decimal | None:
        if decision in {Decision.HOLD, Decision.REVIEW}:
            return None
        return self.limits.max_symbol_notional * {
            Decision.BUY: self.targets.buy, Decision.OVERWEIGHT: self.targets.overweight,
            Decision.UNDERWEIGHT: self.targets.underweight, Decision.SELL: Decimal("0"),
        }[decision]

    def plan(self, *, decision: Decision, symbol: str, reference_price: Decimal,
             account: AccountSnapshot, decision_key: str,
             price_as_of: datetime | None = None) -> OrderIntent | None:
        symbol = canonical_symbol(symbol)
        finite(reference_price, "reference_price", positive=True)
        account.validate()
        target = self.target_notional(decision)
        if target is None:
            return None
        current = account.symbol_notionals.get(symbol, Decimal("0"))
        pending = account.pending_buy_notionals.get(symbol, Decimal("0"))
        delta = target - current - pending
        side = "buy" if delta > 0 else "sell"
        if delta == 0 and decision != Decision.SELL:
            return None
        if decision == Decision.SELL:
            side = "sell"
        if side == "sell" and pending:
            return None
        if side == "buy" and account.pending_sell_quantities.get(symbol, Decimal("0")):
            return None
        slip = self.limits.max_slippage_bps / Decimal("10000")
        raw_limit = reference_price * (1 + slip if side == "buy" else 1 - slip)
        tick = Decimal("0.01") if raw_limit >= 1 else Decimal("0.0001")
        limit = raw_limit.quantize(tick, rounding=ROUND_DOWN if side == "buy" else ROUND_UP)
        if limit <= 0:
            return None
        bound = max(reference_price, limit)
        capacity = self.limits.max_order_notional / bound
        if side == "buy":
            reserved = sum(account.pending_buy_notionals.values(), Decimal("0"))
            budget = min(delta, self.limits.max_order_notional,
                         max(Decimal("0"), account.cash - reserved),
                         max(Decimal("0"), self.limits.max_gross_notional - account.gross_notional - reserved))
            quantity = budget / bound
        else:
            available = account.available_to_sell(symbol)
            desired = available if decision == Decision.SELL else abs(delta) / reference_price
            quantity = min(available, desired, capacity)
        quantity = quantity.quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
        if quantity <= 0:
            return None
        return OrderIntent(symbol, side, quantity, reference_price, order_id(decision_key, symbol), limit, price_as_of)
