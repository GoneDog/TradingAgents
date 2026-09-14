from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import yfinance as yf

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import TradingAgentsGraph

from .broker import BrokerAdapter, OrderReceipt
from .ledger import Ledger
from .models import Decision, RiskLimits
from .oauth_runtime import apply_oauth_only_policy, reject_metered_provider_credentials
from .planner import DecisionPlanner, PositionTargets
from .risk import RiskGate
from .runner import Operator


@dataclass(frozen=True)
class CycleResult:
    symbol: str
    trade_date: str
    decision: Decision
    reference_price: Decimal | None
    submitted: bool
    receipt: OrderReceipt | None = None


def keyless_reference_price(symbol: str) -> Decimal:
    """Get a recent market reference without a paid data-provider credential."""

    history = yf.Ticker(symbol).history(period="5d", auto_adjust=False)
    if history.empty or "Close" not in history:
        raise RuntimeError(f"No price data available for {symbol}")
    closes = history["Close"].dropna()
    if closes.empty:
        raise RuntimeError(f"No valid close available for {symbol}")
    price = Decimal(str(float(closes.iloc[-1])))
    if price <= 0:
        raise RuntimeError(f"Invalid reference price for {symbol}: {price}")
    return price


class UnattendedCycle:
    """One fail-closed research-to-execution iteration.

    The LLM chooses only the TradingAgents rating. Position sizing, order side,
    exposure limits, idempotency, and submission are deterministic.
    """

    def __init__(
        self,
        broker: BrokerAdapter,
        ledger: Ledger,
        limits: RiskLimits,
        *,
        targets: PositionTargets | None = None,
        graph: TradingAgentsGraph | None = None,
    ):
        reject_metered_provider_credentials()
        self.broker = broker
        self.ledger = ledger
        self.limits = limits
        self.planner = DecisionPlanner(limits, targets)
        self.operator = Operator(broker, RiskGate(limits), ledger)
        self.graph = graph or TradingAgentsGraph(
            debug=False,
            config=apply_oauth_only_policy(DEFAULT_CONFIG.copy()),
        )

    def run_once(self, symbol: str, trade_date: str | None = None) -> CycleResult:
        trade_date = trade_date or date.today().isoformat()
        _, signal = self.graph.propagate(symbol, trade_date)

        try:
            decision = Decision(str(signal))
        except ValueError as exc:
            raise RuntimeError(f"Unrecognized TradingAgents decision: {signal!r}") from exc

        if decision in {Decision.HOLD, Decision.REVIEW}:
            return CycleResult(symbol, trade_date, decision, None, False, None)

        reference_price = keyless_reference_price(symbol)
        account = self.broker.snapshot()
        intent = self.planner.plan(
            decision=decision,
            symbol=symbol,
            reference_price=reference_price,
            account=account,
            decision_key=f"{trade_date}:{symbol}",
        )
        if intent is None:
            return CycleResult(symbol, trade_date, decision, reference_price, False, None)

        receipt = self.operator.execute(intent)
        return CycleResult(
            symbol=symbol,
            trade_date=trade_date,
            decision=decision,
            reference_price=reference_price,
            submitted=receipt is not None,
            receipt=receipt,
        )
