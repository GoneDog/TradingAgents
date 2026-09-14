from decimal import Decimal

import pytest

from tradingagents.operator.broker import AccountSnapshot, DryRunBroker
from tradingagents.operator.ledger import Ledger
from tradingagents.operator.models import OrderIntent, RiskLimits
from tradingagents.operator.risk import RiskGate, RiskRejection
from tradingagents.operator.runner import Operator


def limits():
    return RiskLimits(
        max_order_notional=Decimal("100"),
        max_symbol_notional=Decimal("250"),
        max_gross_notional=Decimal("500"),
        max_open_orders=2,
        allow_shorting=False,
    )


def test_operator_deduplicates_order_ids(tmp_path):
    broker = DryRunBroker(cash=Decimal("1000"))
    operator = Operator(broker, RiskGate(limits()), Ledger(tmp_path / "ledger.db"))
    intent = OrderIntent("AAPL", "buy", Decimal("1"), Decimal("50"), "abc-1")

    first = operator.execute(intent)
    second = operator.execute(intent)

    assert first is not None
    assert second is None


def test_operator_retries_pending_intent_only_when_broker_has_no_order(tmp_path):
    broker = DryRunBroker(cash=Decimal("1000"))
    ledger = Ledger(tmp_path / "ledger.db")
    operator = Operator(broker, RiskGate(limits()), ledger)
    intent = OrderIntent("AAPL", "buy", Decimal("1"), Decimal("50"), "recover-1")

    # Simulate dying after the intent was persisted but before broker submission.
    ledger.record_pending(intent)
    receipt = operator.execute(intent)
    assert receipt is not None
    assert receipt.client_order_id == "recover-1"

    # A subsequent run reconciles the broker copy and does not submit again.
    assert operator.execute(intent) is None


def test_risk_gate_rejects_oversized_order():
    gate = RiskGate(limits())
    intent = OrderIntent("AAPL", "buy", Decimal("3"), Decimal("50"), "abc-2")
    account = AccountSnapshot(
        cash=Decimal("1000"),
        gross_notional=Decimal("0"),
        open_orders=0,
        symbol_notionals={},
    )

    with pytest.raises(RiskRejection, match="max_order_notional"):
        gate.validate(intent, account)


def test_risk_gate_prevents_unapproved_short():
    gate = RiskGate(limits())
    intent = OrderIntent("AAPL", "sell", Decimal("1"), Decimal("50"), "abc-3")
    account = AccountSnapshot(
        cash=Decimal("1000"),
        gross_notional=Decimal("0"),
        open_orders=0,
        symbol_notionals={},
    )

    with pytest.raises(RiskRejection, match="short position"):
        gate.validate(intent, account)
