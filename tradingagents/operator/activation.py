from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .rails import RailCapabilities


@dataclass(frozen=True)
class ActivationMandate:
    """One-time capital authorization; routine trades remain autonomous inside it."""

    mode: str = "paper"  # paper | live_capped
    max_capital: Decimal = Decimal("0")
    max_order_notional: Decimal = Decimal("0")
    max_daily_loss: Decimal = Decimal("0")
    allow_withdrawals: bool = False
    allowed_markets: tuple[str, ...] = ()

    def validate(self) -> None:
        if self.mode not in {"paper", "live_capped"}:
            raise ValueError("mode must be paper or live_capped")
        if self.mode == "live_capped":
            if self.max_capital <= 0 or self.max_order_notional <= 0 or self.max_daily_loss <= 0:
                raise ValueError("live_capped requires positive capital/order/loss caps")
            if not self.allowed_markets:
                raise ValueError("live_capped requires an explicit market allowlist")
        if self.allow_withdrawals:
            raise ValueError("autonomous withdrawals are not permitted")


def assert_rail_activatable(cap: RailCapabilities, mandate: ActivationMandate) -> None:
    """Fail closed unless the rail and mandate support the requested autonomy."""
    mandate.validate()
    if mandate.mode == "paper":
        return
    if not cap.unattended:
        raise ValueError(f"{cap.name} requires interactive approval")
    if cap.per_transaction_user_signature:
        raise ValueError(f"{cap.name} requires per-transaction user signatures")
    if cap.auth_mode not in {"oauth2_bearer", "oauth2_bearer_pay_scope"}:
        raise ValueError(f"{cap.name} is outside the OAuth-only production policy")
