from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class WalletRole:
    name: str
    unattended: bool
    max_balance: Decimal | None
    purpose: str


PHANTOM_TREASURY = WalletRole(
    name="phantom_treasury",
    unattended=False,
    max_balance=None,
    purpose="user-controlled treasury; funds delegated agent wallets only by explicit signature",
)

AGENT_HOT_WALLET = WalletRole(
    name="agent_hot_wallet",
    unattended=True,
    max_balance=Decimal("250"),
    purpose="delegated wallet for bounded autonomous execution under policy",
)

REVOLUT_FIAT_RAIL = WalletRole(
    name="revolut_business_fiat",
    unattended=True,
    max_balance=None,
    purpose="OAuth fiat account/exchange/payment rail subject to transaction mandate",
)
