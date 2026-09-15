from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum


class Decision(str, Enum):
    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"
    REVIEW = "REVIEW"


def finite(value: Decimal, name: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")
    if value < 0 or (positive and value == 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'nonnegative'}")
    return value


def canonical_symbol(symbol: str) -> str:
    symbol = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", symbol):
        raise ValueError("only US equity symbols are supported")
    return symbol


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class RiskLimits:
    max_order_notional: Decimal
    max_symbol_notional: Decimal
    max_gross_notional: Decimal
    max_open_orders: int = 5
    allow_shorting: bool = False
    max_price_age_seconds: int = 120
    max_slippage_bps: Decimal = Decimal("50")

    def __post_init__(self) -> None:
        for name in ("max_order_notional", "max_symbol_notional", "max_gross_notional"):
            finite(getattr(self, name), name, positive=True)
        finite(self.max_slippage_bps, "max_slippage_bps")
        if self.max_slippage_bps >= 10000:
            raise ValueError("max_slippage_bps must be below 10000")
        for name in ("max_open_orders", "max_price_age_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.allow_shorting:
            raise ValueError("shorting is not implemented by the unattended operator")


@dataclass(frozen=True)
class PriceQuote:
    price: Decimal
    as_of: datetime

    def validate(self, limits: RiskLimits, now: datetime | None = None) -> None:
        finite(self.price, "quote price", positive=True)
        now = now or utcnow()
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("quote timestamp must be timezone-aware")
        age = (now - self.as_of).total_seconds()
        if age < -5 or age > limits.max_price_age_seconds:
            raise ValueError("quote is stale or in the future")


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str
    quantity: Decimal
    reference_price: Decimal
    client_order_id: str
    limit_price: Decimal | None = None
    price_as_of: datetime | None = None

    @property
    def notional(self) -> Decimal:
        # Retain the original property for callers; risk uses the price bound.
        return self.quantity * max(self.reference_price, self.limit_price or Decimal("0"))
