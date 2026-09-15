from decimal import Decimal

import pytest

from tradingagents.operator.activation import ActivationMandate, assert_rail_activatable
from tradingagents.operator.rails import ALPACA_OAUTH, PHANTOM_CONNECTED, REVOLUT_X_SIGNED_API


def live_mandate():
    return ActivationMandate(
        mode="live_capped",
        max_capital=Decimal("100"),
        max_order_notional=Decimal("20"),
        max_daily_loss=Decimal("5"),
        allowed_markets=("SPY", "BTC/USD"),
    )


def test_oauth_broker_can_be_live_capped():
    assert_rail_activatable(ALPACA_OAUTH, live_mandate())


def test_phantom_cannot_be_unattended_live_rail():
    with pytest.raises(ValueError, match="interactive approval|signatures"):
        assert_rail_activatable(PHANTOM_CONNECTED, live_mandate())


def test_non_oauth_exchange_rejected_by_production_policy():
    with pytest.raises(ValueError, match="OAuth-only"):
        assert_rail_activatable(REVOLUT_X_SIGNED_API, live_mandate())


def test_withdrawals_cannot_be_delegated():
    mandate = ActivationMandate(mode="paper", allow_withdrawals=True)
    with pytest.raises(ValueError, match="withdrawals"):
        mandate.validate()
