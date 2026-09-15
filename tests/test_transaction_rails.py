from decimal import Decimal

import pytest

from tradingagents.operator.mandate import MandateViolation, TransactionMandate
from tradingagents.operator.rails import (
    PHANTOM_CONNECTED,
    PRIVY_DELEGATED,
    REVOLUT_BUSINESS_OAUTH,
    TransferIntent,
)


def mandate():
    return TransactionMandate(
        max_single_transfer=Decimal("25"),
        max_daily_transfer=Decimal("50"),
        max_single_trade=Decimal("50"),
        allowed_assets=frozenset({"USDC"}),
        allowed_destinations=frozenset({"agent-vault"}),
        allow_unattended_transfers=True,
    )


def intent(amount="10", destination="agent-vault"):
    return TransferIntent(
        asset="USDC",
        amount=Decimal(amount),
        destination=destination,
        client_transfer_id="stable-transfer-id",
    )


def test_phantom_cannot_be_used_as_unattended_signer():
    with pytest.raises(MandateViolation, match="requires user signature"):
        mandate().validate_transfer(PHANTOM_CONNECTED, intent(), transferred_today=Decimal("0"))


def test_delegated_wallet_can_execute_inside_mandate():
    mandate().validate_transfer(PRIVY_DELEGATED, intent(), transferred_today=Decimal("5"))


def test_destination_allowlist_blocks_exfiltration():
    with pytest.raises(MandateViolation, match="destination not allowlisted"):
        mandate().validate_transfer(
            PRIVY_DELEGATED, intent(destination="unknown-wallet"), transferred_today=Decimal("0")
        )


def test_daily_cap_blocks_runaway_transfers():
    with pytest.raises(MandateViolation, match="daily transfer cap"):
        mandate().validate_transfer(
            PRIVY_DELEGATED, intent(amount="20"), transferred_today=Decimal("40")
        )


def test_revolut_business_is_capability_compatible_with_unattended_transfer():
    mandate().validate_transfer(
        REVOLUT_BUSINESS_OAUTH, intent(), transferred_today=Decimal("0")
    )
