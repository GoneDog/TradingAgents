from decimal import Decimal

from tradingagents.operator.broker import AccountSnapshot
from tradingagents.operator.models import Decision, RiskLimits
from tradingagents.operator.planner import DecisionPlanner, PositionTargets


def _limits():
    return RiskLimits(
        max_order_notional=Decimal("1000"),
        max_symbol_notional=Decimal("1000"),
        max_gross_notional=Decimal("3000"),
    )


def _account(symbol_notional="0"):
    return AccountSnapshot(
        cash=Decimal("10000"),
        gross_notional=Decimal(symbol_notional),
        open_orders=0,
        symbol_notionals={"AAPL": Decimal(symbol_notional)},
    )


def test_hold_and_review_never_create_orders():
    planner = DecisionPlanner(_limits())
    for decision in (Decision.HOLD, Decision.REVIEW):
        assert planner.plan(
            decision=decision,
            symbol="AAPL",
            reference_price=Decimal("100"),
            account=_account(),
            decision_key="2026-09-14:AAPL",
        ) is None


def test_sell_flattens_existing_long_without_shorting():
    planner = DecisionPlanner(_limits())
    intent = planner.plan(
        decision=Decision.SELL,
        symbol="AAPL",
        reference_price=Decimal("100"),
        account=_account("500"),
        decision_key="2026-09-14:AAPL",
    )
    assert intent is not None
    assert intent.side == "sell"
    assert intent.quantity == Decimal("5.000000")

    # Already flat: SELL means avoid/exit, never open a short.
    assert planner.plan(
        decision=Decision.SELL,
        symbol="AAPL",
        reference_price=Decimal("100"),
        account=_account("0"),
        decision_key="2026-09-14:AAPL",
    ) is None


def test_ratings_map_to_fixed_position_targets():
    planner = DecisionPlanner(
        _limits(),
        PositionTargets(
            buy=Decimal("1.0"),
            overweight=Decimal("0.6"),
            underweight=Decimal("0.25"),
        ),
    )
    intent = planner.plan(
        decision=Decision.OVERWEIGHT,
        symbol="AAPL",
        reference_price=Decimal("100"),
        account=_account("200"),
        decision_key="2026-09-14:AAPL",
    )
    assert intent is not None
    assert intent.side == "buy"
    assert intent.quantity == Decimal("4.000000")


def test_client_order_id_is_stable_for_restart_idempotency():
    planner = DecisionPlanner(_limits())
    kwargs = dict(
        decision=Decision.BUY,
        symbol="AAPL",
        reference_price=Decimal("100"),
        account=_account("0"),
        decision_key="2026-09-14:AAPL",
    )
    assert planner.plan(**kwargs).client_order_id == planner.plan(**kwargs).client_order_id
