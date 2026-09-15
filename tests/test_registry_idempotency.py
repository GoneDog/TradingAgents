from tradingagents.research.models import PromotionState, StrategyCandidate
from tradingagents.research.pipeline import evaluate_and_dispose
from tradingagents.research.registry import StrategyRegistry


def test_repeated_identical_evaluation_is_idempotent(tmp_path):
    registry = StrategyRegistry(tmp_path / "r.db")
    candidate = StrategyCandidate(
        name="repeat",
        hypothesis="test",
        strategy_spec={"kind": "calibration"},
        data_version="v1",
        generator="maker",
        created_at="2026-09-15T00:00:00Z",
    )
    metrics = {
        "trades": 100,
        "profit_factor": 1.2,
        "max_drawdown": 0.1,
        "walk_forward_windows": 4,
        "positive_walk_forward_fraction": 0.75,
        "cost_share_of_gross_profit": 0.2,
        "out_of_sample": 1,
        "monte_carlo_completed": 1,
    }
    evaluate_and_dispose(registry, candidate, validator="checker", metrics=metrics)
    evaluate_and_dispose(registry, candidate, validator="checker", metrics=metrics)
    assert registry.state(candidate.strategy_id) == PromotionState.PAPER
