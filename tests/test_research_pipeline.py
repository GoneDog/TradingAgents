from tradingagents.research.models import PromotionState, StrategyCandidate
from tradingagents.research.pipeline import evaluate_and_dispose
from tradingagents.research.registry import StrategyRegistry


def _candidate(name="c"):
    return StrategyCandidate(
        name=name,
        hypothesis="test",
        strategy_spec={"kind": "calibration"},
        data_version="data-v1",
        generator="maker",
        created_at="2026-09-15T00:00:00Z",
    )


def _pass_metrics():
    return {
        "trades": 100,
        "profit_factor": 1.2,
        "max_drawdown": 0.1,
        "walk_forward_windows": 4,
        "positive_walk_forward_fraction": 0.75,
        "cost_share_of_gross_profit": 0.2,
        "out_of_sample": 1,
        "monte_carlo_completed": 1,
    }


def test_pass_goes_to_paper(tmp_path):
    registry = StrategyRegistry(tmp_path / "r.db")
    c = _candidate("pass")
    result = evaluate_and_dispose(
        registry, c, validator="checker", metrics=_pass_metrics()
    )
    assert result.passed
    assert registry.state(c.strategy_id) == PromotionState.PAPER


def test_fail_is_rejected(tmp_path):
    registry = StrategyRegistry(tmp_path / "r.db")
    c = _candidate("fail")
    metrics = _pass_metrics()
    metrics["max_drawdown"] = 0.5
    result = evaluate_and_dispose(
        registry, c, validator="checker", metrics=metrics
    )
    assert not result.passed
    assert registry.state(c.strategy_id) == PromotionState.REJECTED
