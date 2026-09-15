from decimal import Decimal

import pytest

from tradingagents.operator.broker import AccountSnapshot, DryRunBroker
from tradingagents.operator.ledger import Ledger
from tradingagents.operator.models import OrderIntent, RiskLimits, utcnow
from tradingagents.operator.risk import RiskGate, RiskRejection
from tradingagents.operator.runner import Operator


def limits():
    return RiskLimits(Decimal("100"), Decimal("250"), Decimal("500"), max_open_orders=2)


def intent(key, side="buy", quantity="1"):
    return OrderIntent("AAPL", side, Decimal(quantity), Decimal("50"), key, Decimal("50"), utcnow())


def test_operator_deduplicates_order_ids(tmp_path):
    broker = DryRunBroker(cash=Decimal("1000"))
    operator = Operator(broker, RiskGate(limits()), Ledger(tmp_path / "ledger.db"))
    order = intent("abc-1")
    assert operator.execute(order) is not None
    assert operator.execute(order) is None


def test_operator_retries_only_definitely_unsubmitted_pending_intent(tmp_path):
    broker = DryRunBroker(cash=Decimal("1000"))
    ledger = Ledger(tmp_path / "ledger.db")
    operator = Operator(broker, RiskGate(limits()), ledger)
    order = intent("recover-1")
    ledger.record_pending(order)
    assert operator.execute(order).client_order_id == "recover-1"
    assert operator.execute(order) is None


def test_risk_gate_rejects_oversized_order():
    account = AccountSnapshot(Decimal("1000"), Decimal("0"), 0, {})
    with pytest.raises(RiskRejection, match="max_order_notional"):
        RiskGate(limits()).validate(intent("abc-2", quantity="3"), account)


def test_risk_gate_prevents_unapproved_short():
    account = AccountSnapshot(Decimal("1000"), Decimal("0"), 0, {})
    with pytest.raises(RiskRejection, match="short position"):
        RiskGate(limits()).validate(intent("abc-3", side="sell"), account)
