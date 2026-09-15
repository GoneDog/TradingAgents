from decimal import Decimal

from tradingagents.operator.broker import AccountSnapshot
from tradingagents.operator.models import Decision, RiskLimits
from tradingagents.operator.planner import DecisionPlanner, PositionTargets


def _limits():
    return RiskLimits(Decimal("1000"), Decimal("1000"), Decimal("3000"), max_slippage_bps=Decimal("0"))


def _account(held="0"):
    quantity = Decimal(held)
    return AccountSnapshot(Decimal("10000"), quantity * 100, 0,
        {"AAPL": quantity * 100}, symbol_quantities={"AAPL": quantity})


def _plan(planner, decision, held="0", price="100"):
    return planner.plan(decision=decision, symbol="AAPL", reference_price=Decimal(price),
        account=_account(held), decision_key="2026-09-14:AAPL")


def test_hold_and_review_never_create_orders():
    for decision in (Decision.HOLD, Decision.REVIEW):
        assert _plan(DecisionPlanner(_limits()), decision) is None


def test_sell_flattens_existing_long_without_shorting():
    planner = DecisionPlanner(_limits())
    order = _plan(planner, Decision.SELL, "5")
    assert order.side == "sell" and order.quantity == Decimal("5.000000")
    assert _plan(planner, Decision.SELL) is None


def test_ratings_map_to_fixed_position_targets():
    planner = DecisionPlanner(_limits(), PositionTargets(Decimal("1.0"), Decimal("0.6"), Decimal("0.25")))
    order = _plan(planner, Decision.OVERWEIGHT, "2")
    assert order.side == "buy" and order.quantity == Decimal("4.000000")


def test_client_order_id_is_stable_when_reference_price_changes():
    planner = DecisionPlanner(_limits())
    assert _plan(planner, Decision.BUY).client_order_id == _plan(planner, Decision.BUY, price="101").client_order_id
