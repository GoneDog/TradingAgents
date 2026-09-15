from tradingagents.research import (
    PromotionState,
    StrategyCandidate,
    StrategyRegistry,
    validate_candidate,
)


def candidate():
    return StrategyCandidate(
        name="example",
        hypothesis="A falsifiable market hypothesis",
        strategy_spec={"entry": "signal", "exit": "inverse_signal"},
        data_version="dataset-sha",
        generator="maker-agent",
        created_at="2026-09-15T00:00:00Z",
    )


def passing_metrics():
    return {
        "trades": 100,
        "profit_factor": 1.4,
        "max_drawdown": 0.08,
        "walk_forward_windows": 5,
        "positive_walk_forward_fraction": 0.8,
        "cost_share_of_gross_profit": 0.15,
        "out_of_sample": 1,
        "monte_carlo_completed": 1,
    }


def test_strategy_id_is_content_stable():
    assert candidate().strategy_id == candidate().strategy_id


def test_validator_rejects_missing_robustness_checks():
    metrics = passing_metrics()
    metrics["out_of_sample"] = 0
    metrics["monte_carlo_completed"] = 0
    result = validate_candidate(candidate(), validator="checker-agent", metrics=metrics)
    assert not result.passed
    assert "missing_out_of_sample_test" in result.reasons
    assert "missing_monte_carlo" in result.reasons


def test_registry_requires_explicit_promotion_path(tmp_path):
    c = candidate()
    registry = StrategyRegistry(tmp_path / "research.db")
    registry.register(c)
    result = validate_candidate(c, validator="checker-agent", metrics=passing_metrics())
    registry.record_validation(result)
    registry.transition(c.strategy_id, PromotionState.PAPER, actor="promotion-gate", reason="passed")
    assert registry.state(c.strategy_id) == PromotionState.PAPER
    registry.transition(c.strategy_id, PromotionState.LIVE_CAPPED, actor="capital-gate", reason="forward pass")
    assert registry.state(c.strategy_id) == PromotionState.LIVE_CAPPED
