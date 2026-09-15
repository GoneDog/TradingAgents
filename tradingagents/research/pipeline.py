from __future__ import annotations

from .models import PromotionState, StrategyCandidate, ValidationResult
from .registry import StrategyRegistry
from .validation import ValidationPolicy, validate_candidate


def evaluate_and_dispose(
    registry: StrategyRegistry,
    candidate: StrategyCandidate,
    *,
    validator: str,
    metrics: dict[str, float],
    policy: ValidationPolicy | None = None,
) -> ValidationResult:
    """Register, validate and deterministically disposition a strategy candidate."""
    registry.register(candidate)
    result = validate_candidate(
        candidate,
        validator=validator,
        metrics=metrics,
        policy=policy,
    )
    registry.record_validation(result)

    target = PromotionState.PAPER if result.passed else PromotionState.REJECTED
    reason = "validation_passed" if result.passed else ",".join(result.reasons)
    registry.transition(
        candidate.strategy_id,
        target,
        actor="deterministic-promotion-gate",
        reason=reason,
    )
    return result
