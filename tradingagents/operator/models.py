from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class Decision(str, Enum):
    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"
    REVIEW = "REVIEW"


@dataclass(frozen=True)
class RiskLimits:
    max_order_notional: Decimal
    max_symbol_notional: Decimal
    max_gross_notional: Decimal
    max_open_orders: int = 5
    allow_shorting: bool = False


@dataclass(frozen=True)
class OrderIntent:
    symbol: str
    side: str
    quantity: Decimal
    reference_price: Decimal
    client_order_id: str

    @property
    def notional(self) -> Decimal:
        return self.quantity * self.reference_price
