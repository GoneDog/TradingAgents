from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .rails import RailCapabilities, TradeIntent, TransferIntent


class MandateViolation(RuntimeError):
    pass


@dataclass(frozen=True)
class TransactionMandate:
    max_single_transfer: Decimal
    max_daily_transfer: Decimal
    max_single_trade: Decimal
    allowed_assets: frozenset[str] = field(default_factory=frozenset)
    allowed_destinations: frozenset[str] = field(default_factory=frozenset)
    allow_unattended_transfers: bool = False
    allow_unattended_trades: bool = True

    def validate_transfer(
        self,
        rail: RailCapabilities,
        intent: TransferIntent,
        *,
        transferred_today: Decimal,
    ) -> None:
        if not rail.transfer:
            raise MandateViolation(f"{rail.name} cannot transfer")
        if intent.amount <= 0:
            raise MandateViolation("transfer amount must be positive")
        if self.allowed_assets and intent.asset.upper() not in self.allowed_assets:
            raise MandateViolation("asset not allowlisted")
        if self.allowed_destinations and intent.destination not in self.allowed_destinations:
            raise MandateViolation("destination not allowlisted")
        if intent.amount > self.max_single_transfer:
            raise MandateViolation("single transfer exceeds mandate")
        if transferred_today + intent.amount > self.max_daily_transfer:
            raise MandateViolation("daily transfer cap exceeded")
        if rail.per_transaction_user_signature:
            raise MandateViolation("rail requires user signature")
        if not rail.unattended or not self.allow_unattended_transfers:
            raise MandateViolation("unattended transfers are not authorized")

    def validate_trade(self, rail: RailCapabilities, intent: TradeIntent) -> None:
        if not rail.trade:
            raise MandateViolation(f"{rail.name} cannot trade")
        if intent.quantity <= 0:
            raise MandateViolation("trade quantity must be positive")
        if intent.quantity > self.max_single_trade:
            raise MandateViolation("trade exceeds mandate")
        if not rail.unattended or not self.allow_unattended_trades:
            raise MandateViolation("unattended trading is not authorized")
