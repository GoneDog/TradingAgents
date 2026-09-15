from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from .broker import BrokerAdapter, OrderReceipt
from .ledger import Ledger
from .models import Decision, RiskLimits, canonical_symbol
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


class UnattendedCycle:
    """One account-scoped, durable decision cycle. No scheduler or OAuth bridge."""

    def __init__(self, broker: BrokerAdapter, ledger: Ledger, limits: RiskLimits,
                 *, targets: PositionTargets | None = None, graph=None):
        reject_metered_provider_credentials()
        self.broker = broker
        self.ledger = ledger
        self.limits = limits
        self.planner = DecisionPlanner(limits, targets)
        self.operator = Operator(broker, RiskGate(limits), ledger)
        if graph is None:
            # Keep deterministic safety/recovery tests independent of LLM imports.
            from tradingagents.default_config import DEFAULT_CONFIG
            from tradingagents.graph.trading_graph import TradingAgentsGraph
            graph = TradingAgentsGraph(debug=False, config=apply_oauth_only_policy(DEFAULT_CONFIG.copy()))
        self.graph = graph

    def run_once(self, symbol: str, trade_date: str | None = None, *, decision_version: str = "v1") -> CycleResult:
        symbol = canonical_symbol(symbol)
        today = datetime.now(ZoneInfo("America/New_York")).date().isoformat()
        trade_date = trade_date or today
        if trade_date != today:
            raise ValueError("execution requires today's New York trading date; use the research graph for historical analysis")
        if not decision_version or len(decision_version) > 64 or ":" in decision_version:
            raise ValueError("an explicit decision version without ':' is required")
        key = f"{trade_date}:{symbol}:{decision_version}"
        with self.ledger.exclusive():
            saved = self.ledger.get_decision(key)
            if saved is not None:
                intent = self.ledger.get_intent(saved["client_order_id"]) if saved["client_order_id"] else None
                if intent is None:
                    self.operator.preflight()
                    return CycleResult(symbol, trade_date, Decision(saved["decision"]), None, False)
                receipt = self.operator.execute(intent)
                return CycleResult(symbol, trade_date, Decision(saved["decision"]), intent.reference_price, receipt is not None, receipt)
            self.operator.preflight()
            _, signal = self.graph.propagate(symbol, trade_date)
            try:
                decision = signal if isinstance(signal, Decision) else Decision(str(signal))
            except ValueError as exc:
                raise RuntimeError(f"Unrecognized TradingAgents decision: {signal!r}") from exc
            intent = None
            price = None
            if decision not in {Decision.HOLD, Decision.REVIEW}:
                # Never size execution from a daily Yahoo close.
                quote = self.broker.quote(symbol)
                quote.validate(self.limits)
                account = self.operator.preflight()
                price = quote.price
                intent = self.planner.plan(decision=decision, symbol=symbol,
                    reference_price=price, price_as_of=quote.as_of,
                    account=account, decision_key=key)
            self.ledger.record_decision(key, symbol, decision, intent)
            receipt = self.operator.execute(intent) if intent else None
            return CycleResult(symbol, trade_date, decision, price, receipt is not None, receipt)
