import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D

import pytest

from tradingagents.operator.broker import AccountSnapshot, DryRunBroker, OrderReceipt
from tradingagents.operator.cycle import UnattendedCycle
from tradingagents.operator.ledger import IntentConflict, Ledger, ReconciliationRequired
from tradingagents.operator.models import Decision, OrderIntent, PriceQuote, RiskLimits, utcnow
from tradingagents.operator.oauth_runtime import (
    OAuthRuntimeConfig,
    apply_oauth_only_policy,
    reject_metered_provider_credentials,
)
from tradingagents.operator.planner import DecisionPlanner, PositionTargets
from tradingagents.operator.risk import RiskGate, RiskRejection
from tradingagents.operator.runner import Operator


def limits(**kwargs):
    return replace(RiskLimits(D("1000"), D("1000"), D("1000"), max_slippage_bps=D("0")), **kwargs)


def intent(key="one", *, qty="9", price="100", side="buy", symbol="AAPL"):
    return OrderIntent(symbol, side, D(qty), D(price), key, D(price), utcnow())


def account(held="0", price="100", **kwargs):
    qty = D(held)
    return replace(AccountSnapshot(D("10000"), qty * D(price), 0,
        {"AAPL": qty * D(price)}, symbol_quantities={"AAPL": qty}), **kwargs)


def test_pending_buys_reserve_symbol_and_gross():
    a = account(open_orders=1, open_order_ids=frozenset({"old"}), pending_buy_notionals={"AAPL": D("900")})
    with pytest.raises(RiskRejection, match="symbol exposure"):
        RiskGate(limits()).validate(intent("new"), a)
    with pytest.raises(RiskRejection, match="gross exposure"):
        RiskGate(limits()).validate(intent("other", symbol="MSFT"), a)


def test_pending_buys_reserve_cash():
    a = account(cash=D("1000"), open_orders=1, open_order_ids=frozenset({"old"}), pending_buy_notionals={"MSFT": D("900")})
    with pytest.raises(RiskRejection, match="available cash"):
        RiskGate(limits(max_gross_notional=D("10000"))).validate(intent(qty="2"), a)


def test_share_based_exit_with_mismatched_mark_and_quote():
    a = account("10", "110")
    policy = limits(max_order_notional=D("2000"), max_symbol_notional=D("2000"), max_gross_notional=D("2000"))
    plan = DecisionPlanner(policy).plan(decision=Decision.SELL, symbol="AAPL", reference_price=D("100"), account=a, decision_key="exit", price_as_of=utcnow())
    assert plan.quantity == 10
    RiskGate(policy).validate(plan, a)
    with pytest.raises(RiskRejection, match="short position"):
        RiskGate(policy).validate(replace(plan, quantity=D("11")), a)


def test_pending_sells_and_broker_availability_are_not_double_subtracted():
    a = account("10", open_orders=1, open_order_ids=frozenset({"old"}), pending_sell_quantities={"AAPL": D("4")}, available_quantities={"AAPL": D("6")})
    assert a.available_to_sell("AAPL") == 6
    RiskGate(limits()).validate(intent(side="sell", qty="6"), a)
    with pytest.raises(RiskRejection, match="reserved shares"):
        RiskGate(limits()).validate(intent(side="sell", qty="7"), a)


def test_sale_remains_allowed_when_mark_to_market_exceeds_gross_cap():
    RiskGate(limits()).validate(intent(side="sell", qty="1"), account("20"))


def test_open_sell_does_not_free_gross_capacity_before_fill():
    a = account("10", open_orders=1, open_order_ids=frozenset({"exit"}), pending_sell_quantities={"AAPL": D("10")})
    with pytest.raises(RiskRejection, match="gross exposure"):
        RiskGate(limits()).validate(intent(symbol="MSFT", qty="1"), a)


def test_missing_position_quantities_fail_closed():
    with pytest.raises(RiskRejection, match="quantities are missing"):
        RiskGate(limits()).validate(intent(), replace(account("10"), symbol_quantities={}))


def test_incomplete_open_order_snapshot_fails_closed():
    with pytest.raises(RiskRejection, match="reconciliation is incomplete"):
        RiskGate(limits()).validate(intent(), account(open_orders=1))


@pytest.mark.parametrize("value", [D("NaN"), D("Infinity"), D("-Infinity"), D("-1"), D("0")])
def test_invalid_numeric_order_input_fails_closed(value):
    with pytest.raises(RiskRejection):
        RiskGate(limits()).validate(replace(intent(), quantity=value), account())


@pytest.mark.parametrize("seconds", [121, -10])
def test_stale_or_future_quotes_fail_closed(seconds):
    with pytest.raises(RiskRejection, match="stale or in the future"):
        RiskGate(limits()).validate(replace(intent(), price_as_of=utcnow() - timedelta(seconds=seconds)), account())


def test_missing_quote_timestamp_and_market_orders_fail_closed():
    with pytest.raises(RiskRejection, match="timestamped"):
        RiskGate(limits()).validate(replace(intent(), price_as_of=None), account())
    with pytest.raises(RiskRejection, match="finite Decimal"):
        RiskGate(limits()).validate(replace(intent(), limit_price=None), account())


def test_actual_price_bound_drives_cash_and_order_limit():
    policy = limits(max_slippage_bps=D("50"))
    with pytest.raises(RiskRejection, match="max_order_notional"):
        RiskGate(policy).validate(replace(intent(qty="10"), limit_price=D("100.50")), account())


def test_excess_slippage_is_rejected():
    with pytest.raises(RiskRejection, match="slippage"):
        RiskGate(limits()).validate(replace(intent(), limit_price=D("101")), account())


def test_planner_accounts_for_pending_buys_and_order_cap():
    a = account(open_orders=1, open_order_ids=frozenset({"old"}), pending_buy_notionals={"AAPL": D("700")})
    p = DecisionPlanner(limits(max_order_notional=D("200"))).plan(decision=Decision.BUY, symbol="AAPL", reference_price=D("100"), account=a, decision_key="test")
    assert p.quantity == 2


def test_sell_oversized_position_is_chunked_by_share_count():
    p = DecisionPlanner(limits(max_order_notional=D("100"))).plan(decision=Decision.SELL, symbol="AAPL", reference_price=D("100"), account=account("10", "110"), decision_key="sell")
    assert p.quantity == 1


def test_retry_identity_ignores_price_rating_and_target():
    planner = DecisionPlanner(limits())
    kwargs = {"symbol": "AAPL", "account": account(), "decision_key": "same"}
    one = planner.plan(decision=Decision.BUY, reference_price=D("100"), **kwargs)
    two = planner.plan(decision=Decision.OVERWEIGHT, reference_price=D("101"), **kwargs)
    assert one.client_order_id == two.client_order_id
    three = planner.plan(decision=Decision.BUY, reference_price=D("100"), **{**kwargs, "decision_key": "same:v2"})
    assert three.client_order_id != one.client_order_id


def test_immutable_payload_conflict_is_not_overwritten(tmp_path):
    ledger = Ledger(tmp_path / "state.db")
    one = intent()
    ledger.record_pending(one)
    with pytest.raises(IntentConflict):
        ledger.record_pending(replace(one, quantity=D("1")))
    assert ledger.get_intent(one.client_order_id) == one


def test_original_prepared_intent_survives_restart(tmp_path):
    path = tmp_path / "state.db"
    one = intent()
    Ledger(path).record_pending(one)
    broker = DryRunBroker()
    op = Operator(broker, RiskGate(limits()), Ledger(path))
    assert op.execute(one) is not None
    assert op.execute(one) is None
    assert len(broker._orders) == 1


class UncertainBroker(DryRunBroker):
    def __init__(self, accepted=False):
        super().__init__()
        self.calls = 0
        self.accepted = accepted

    def submit(self, order):
        self.calls += 1
        if self.accepted:
            super().submit(order)
        raise TimeoutError("response lost")


@pytest.mark.parametrize("accepted", [False, True])
def test_timeout_never_creates_a_second_submission(tmp_path, accepted):
    broker = UncertainBroker(accepted)
    path = tmp_path / "state.db"
    op = Operator(broker, RiskGate(limits()), Ledger(path))
    one = intent()
    with pytest.raises(ReconciliationRequired, match="unknown"):
        op.execute(one)
    recovered = Operator(broker, RiskGate(limits()), Ledger(path))
    if accepted:
        assert recovered.execute(one) is None
    else:
        with pytest.raises(ReconciliationRequired, match="unresolved"):
            recovered.execute(one)
        with pytest.raises(ReconciliationRequired):
            recovered.execute(intent("new", symbol="MSFT"))
    assert broker.calls == 1


def test_crash_after_submitting_marker_does_not_retry_on_404(tmp_path):
    ledger = Ledger(tmp_path / "state.db")
    one = intent()
    ledger.record_pending(one)
    ledger.set_status(one.client_order_id, "submitting")
    with pytest.raises(ReconciliationRequired, match="unresolved"):
        Operator(DryRunBroker(), RiskGate(limits()), ledger).execute(one)


def test_unknown_receipt_can_reconcile_to_filled(tmp_path):
    ledger = Ledger(tmp_path / "state.db")
    one = intent()
    ledger.record_pending(one)
    ledger.set_status(one.client_order_id, "unknown")
    class FilledBroker(DryRunBroker):
        def lookup(self, key):
            return OrderReceipt(key, "broker-filled", "filled")
    assert Operator(FilledBroker(), RiskGate(limits()), ledger).execute(one) is None
    assert ledger.get_order(one.client_order_id)["status"] == "filled"


def test_account_switch_is_rejected(tmp_path):
    ledger = Ledger(tmp_path / "state.db")
    ledger.bind_account("different-account")
    broker = DryRunBroker()
    with pytest.raises(ReconciliationRequired, match="different account"):
        Operator(broker, RiskGate(limits()), ledger).execute(intent())
    assert not broker._orders


def test_broker_order_without_local_intent_is_not_adopted(tmp_path):
    broker = DryRunBroker()
    one = intent()
    broker.submit(one)
    with pytest.raises(ReconciliationRequired, match="missing from this ledger"):
        Operator(broker, RiskGate(limits()), Ledger(tmp_path / "new.db")).execute(one)


def test_concurrent_workers_share_exposure_lock(tmp_path):
    path = tmp_path / "state.db"
    broker = DryRunBroker()
    ledgers = [Ledger(path), Ledger(path)]
    orders = [intent("one"), intent("two")]
    def execute(index):
        try:
            return Operator(broker, RiskGate(limits()), ledgers[index]).execute(orders[index])
        except RiskRejection:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(execute, [0, 1]))
    assert sum(r is not None for r in results) == 1
    assert len(broker._orders) == 1


def test_concurrent_same_intent_has_one_submission(tmp_path):
    path = tmp_path / "state.db"
    broker = DryRunBroker()
    ledgers = [Ledger(path), Ledger(path)]
    one = intent()
    def execute(index):
        return Operator(broker, RiskGate(limits()), ledgers[index]).execute(one)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(execute, [0, 1]))
    assert sum(r is not None for r in results) == 1
    assert len(broker._orders) == 1


class Graph:
    def __init__(self, signal="Buy"):
        self.calls = 0
        self.signal = signal

    def propagate(self, symbol, trade_date):
        self.calls += 1
        return {}, self.signal


class QuotedBroker(DryRunBroker):
    def __init__(self):
        super().__init__()
        self.price = D("100")
        self.quote_calls = 0

    def quote(self, symbol):
        self.quote_calls += 1
        return PriceQuote(self.price, utcnow())


def test_cycle_restart_reuses_decision_without_research_or_repricing(tmp_path):
    path = tmp_path / "state.db"
    broker, graph = QuotedBroker(), Graph()
    cycle = UnattendedCycle(broker, Ledger(path), limits(), graph=graph)
    first = cycle.run_once("aapl")
    broker.price = D("101")
    graph.signal = "Sell"
    second = UnattendedCycle(broker, Ledger(path), limits(), graph=graph).run_once("AAPL")
    assert first.submitted and not second.submitted
    assert second.decision == Decision.BUY
    assert second.reference_price == D("100")
    assert graph.calls == broker.quote_calls == 1
    assert len(broker._orders) == 1


@pytest.mark.parametrize("signal", ["Hold", "REVIEW"])
def test_no_trade_decisions_are_durable(tmp_path, signal):
    graph, broker = Graph(signal), QuotedBroker()
    cycle = UnattendedCycle(broker, Ledger(tmp_path / "state.db"), limits(), graph=graph)
    assert not cycle.run_once("AAPL").submitted
    graph.signal = "Buy"
    assert not cycle.run_once("AAPL").submitted
    assert graph.calls == 1
    assert broker.quote_calls == 0


def test_unrecognized_rating_does_not_create_order(tmp_path):
    broker = QuotedBroker()
    cycle = UnattendedCycle(broker, Ledger(tmp_path / "state.db"), limits(), graph=Graph("BUY SOMETHING"))
    with pytest.raises(RuntimeError, match="Unrecognized"):
        cycle.run_once("AAPL")
    assert not broker._orders


def test_historical_date_does_not_execute(tmp_path):
    broker = QuotedBroker()
    cycle = UnattendedCycle(broker, Ledger(tmp_path / "state.db"), limits(), graph=Graph())
    with pytest.raises(ValueError, match="historical"):
        cycle.run_once("AAPL", "2000-01-01")
    assert not broker._orders


def test_nonempty_legacy_ledger_requires_reconciliation(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE orders (client_order_id TEXT, status TEXT)")
        con.execute("INSERT INTO orders VALUES ('old','pending')")
    with pytest.raises(ReconciliationRequired, match="legacy ledger"):
        Ledger(path)
    with sqlite3.connect(path) as con:
        assert con.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1


def test_empty_legacy_ledger_can_migrate(tmp_path):
    path = tmp_path / "empty.db"
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE orders (client_order_id TEXT, status TEXT)")
    ledger = Ledger(path)
    ledger.record_pending(intent())
    assert ledger.has_order("one")


def test_empty_explicit_environment_does_not_read_process_keys(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "forbidden-placeholder")
    reject_metered_provider_credentials({})
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        reject_metered_provider_credentials()


def test_policy_clears_tool_level_paid_vendor_override():
    result = apply_oauth_only_policy({"tool_vendors": {"get_news": "alpha_vantage"}})
    assert result["tool_vendors"] == {}
    assert result["llm_provider"] == "openai_compatible"


@pytest.mark.parametrize("url", ["https://example.com/v1", "http://user:secret@localhost/v1", "http://localhost/v1?key=secret"])
def test_invalid_bridge_urls_are_rejected(url):
    with pytest.raises(ValueError):
        OAuthRuntimeConfig(backend_url=url).validate()


@pytest.mark.parametrize("kwargs", [{"allow_shorting": True}, {"max_open_orders": 0}, {"max_slippage_bps": D("NaN")}])
def test_invalid_risk_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        limits(**kwargs)


def test_invalid_target_ordering_is_rejected():
    with pytest.raises(ValueError, match="ordered"):
        PositionTargets(buy=D("0.2"), overweight=D("0.6"))
