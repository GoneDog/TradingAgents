from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from hashlib import sha256

from .broker import AccountSnapshot
from .models import Decision, OrderIntent, RiskLimits


@dataclass(frozen=True)
class PositionTargets:
    """Target exposure as a fraction of the per-symbol risk ceiling.

    LLM ratings choose among these fixed targets; they never choose quantity.
    SELL means flat, never short. HOLD and REVIEW produce no order.
    """

    buy: Decimal = Decimal("1.00")
    overweight: Decimal = Decimal("0.60")
    underweight: Decimal = Decimal("0.25")

    def __post_init__(self) -> None:
        for name, value in (
            ("buy", self.buy),
            ("overweight", self.overweight),
            ("underweight", self.underweight),
        ):
            if value < 0 or value > 1:
                raise ValueError(f"{name} target must be between 0 and 1")


class DecisionPlanner:
    """Translate a TradingAgents rating into one deterministic order intent."""

    def __init__(self, limits: RiskLimits, targets: PositionTargets | None = None):
        self.limits = limits
        self.targets = targets or PositionTargets()

    def target_notional(self, decision: Decision) -> Decimal | None:
        if decision in {Decision.HOLD, Decision.REVIEW}:
            return None
        fractions = {
            Decision.BUY: self.targets.buy,
            Decision.OVERWEIGHT: self.targets.overweight,
            Decision.UNDERWEIGHT: self.targets.underweight,
            Decision.SELL: Decimal("0"),
        }
        return self.limits.max_symbol_notional * fractions[decision]

    def plan(
        self,
        *,
        decision: Decision,
        symbol: str,
        reference_price: Decimal,
        account: AccountSnapshot,
        decision_key: str,
    ) -> OrderIntent | None:
        if reference_price <= 0:
            raise ValueError("reference_price must be positive")

        target = self.target_notional(decision)
        if target is None:
            return None

        current = max(account.symbol_notionals.get(symbol, Decimal("0")), Decimal("0"))
        delta = target - current
        if delta == 0:
            return None

        side = "buy" if delta > 0 else "sell"
        quantity = (abs(delta) / reference_price).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)
        if quantity <= 0:
            return None

        # Stable across process restarts for the same decision and target state.
        raw_id = f"{decision_key}|{symbol}|{decision.value}|{target}|{reference_price}"
        client_order_id = "ta-" + sha256(raw_id.encode("utf-8")).hexdigest()[:24]

        return OrderIntent(
            symbol=symbol,
            side=side,
            quantity=quantity,
            reference_price=reference_price,
            client_order_id=client_order_id,
        )
