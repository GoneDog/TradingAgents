from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Protocol


class RailKind(str, Enum):
    BROKER = "broker"
    BANK = "bank"
    EXCHANGE = "exchange"
    SELF_CUSTODY = "self_custody"
    DELEGATED_WALLET = "delegated_wallet"


@dataclass(frozen=True)
class RailCapabilities:
    name: str
    kind: RailKind
    read_balances: bool
    trade: bool
    transfer: bool
    unattended: bool
    per_transaction_user_signature: bool
    auth_mode: str


@dataclass(frozen=True)
class TransferIntent:
    asset: str
    amount: Decimal
    destination: str
    client_transfer_id: str


@dataclass(frozen=True)
class TradeIntent:
    market: str
    side: str
    quantity: Decimal
    client_trade_id: str


class TransactionRail(Protocol):
    @property
    def capabilities(self) -> RailCapabilities: ...

    def balance(self, asset: str) -> Decimal: ...

    def submit_transfer(self, intent: TransferIntent): ...

    def submit_trade(self, intent: TradeIntent): ...


ALPACA_OAUTH = RailCapabilities(
    name="alpaca",
    kind=RailKind.BROKER,
    read_balances=True,
    trade=True,
    transfer=False,
    unattended=True,
    per_transaction_user_signature=False,
    auth_mode="oauth2_bearer",
)

REVOLUT_BUSINESS_OAUTH = RailCapabilities(
    name="revolut_business",
    kind=RailKind.BANK,
    read_balances=True,
    trade=True,  # currency exchange
    transfer=True,
    unattended=True,
    per_transaction_user_signature=False,
    auth_mode="oauth2_bearer_pay_scope",
)

REVOLUT_X_SIGNED_API = RailCapabilities(
    name="revolut_x",
    kind=RailKind.EXCHANGE,
    read_balances=True,
    trade=True,
    transfer=False,
    unattended=True,
    per_transaction_user_signature=False,
    auth_mode="api_key_ed25519_signature",
)

PHANTOM_CONNECTED = RailCapabilities(
    name="phantom",
    kind=RailKind.SELF_CUSTODY,
    read_balances=True,
    trade=False,
    transfer=True,
    unattended=False,
    per_transaction_user_signature=True,
    auth_mode="wallet_connect_user_signature",
)

PRIVY_DELEGATED = RailCapabilities(
    name="privy_delegated",
    kind=RailKind.DELEGATED_WALLET,
    read_balances=True,
    trade=True,
    transfer=True,
    unattended=True,
    per_transaction_user_signature=False,
    auth_mode="delegated_server_signer_policy",
)
