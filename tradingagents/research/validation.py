from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json

from .models import StrategyCandidate, ValidationResult


@dataclass(frozen=True)
class ValidationPolicy:
    min_trades: int = 30
    min_profit_factor: float = 1.05
    max_drawdown: float = 0.15
    min_walk_forward_windows: int = 3
    min_positive_walk_forward_fraction: float = 0.60
    max_cost_share_of_gross_profit: float = 0.35
    require_out_of_sample: bool = True
    require_monte_carlo: bool = True


def validate_candidate(
    candidate: StrategyCandidate,
    *,
    validator: str,
    metrics: dict[str, float],
    policy: ValidationPolicy | None = None,
) -> ValidationResult:
    """Apply promotion gates without asking an LLM to grade its own strategy.

    Metrics are produced by the backtest/validation engine. This function is
    deliberately boring: promotion criteria are deterministic and auditable.
    """
    policy = policy or ValidationPolicy()
    reasons: list[str] = []

    if metrics.get("trades", 0) < policy.min_trades:
        reasons.append("insufficient_trade_count")
    if metrics.get("profit_factor", 0) < policy.min_profit_factor:
        reasons.append("profit_factor_below_floor")
    if metrics.get("max_drawdown", 1) > policy.max_drawdown:
        reasons.append("drawdown_above_cap")
    windows = metrics.get("walk_forward_windows", 0)
    if windows < policy.min_walk_forward_windows:
        reasons.append("insufficient_walk_forward_windows")
    if metrics.get("positive_walk_forward_fraction", 0) < policy.min_positive_walk_forward_fraction:
        reasons.append("walk_forward_instability")
    if metrics.get("cost_share_of_gross_profit", 1) > policy.max_cost_share_of_gross_profit:
        reasons.append("costs_consume_edge")
    if policy.require_out_of_sample and metrics.get("out_of_sample", 0) != 1:
        reasons.append("missing_out_of_sample_test")
    if policy.require_monte_carlo and metrics.get("monte_carlo_completed", 0) != 1:
        reasons.append("missing_monte_carlo")

    fingerprint = sha256(
        json.dumps(metrics, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:20]
    return ValidationResult(
        strategy_id=candidate.strategy_id,
        validator=validator,
        passed=not reasons,
        reasons=tuple(reasons),
        metrics=dict(metrics),
        test_fingerprint=fingerprint,
    )
