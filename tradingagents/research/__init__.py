"""Autonomous strategy research and validation primitives."""

from .backtest import (
    BacktestResult,
    Trade,
    backtest_binary_signal,
    monte_carlo_drawdowns,
    positive_fraction,
    walk_forward_slices,
)
from .calibration import (
    CalibrationConfig,
    dataset_fingerprint,
    evaluate_sma_calibration,
    sma_signal,
)
from .models import PromotionState, StrategyCandidate, ValidationResult
from .pipeline import evaluate_and_dispose
from .registry import StrategyRegistry
from .validation import ValidationPolicy, validate_candidate

__all__ = [
    "BacktestResult",
    "CalibrationConfig",
    "PromotionState",
    "StrategyCandidate",
    "StrategyRegistry",
    "Trade",
    "ValidationPolicy",
    "ValidationResult",
    "backtest_binary_signal",
    "dataset_fingerprint",
    "evaluate_and_dispose",
    "evaluate_sma_calibration",
    "monte_carlo_drawdowns",
    "positive_fraction",
    "sma_signal",
    "validate_candidate",
    "walk_forward_slices",
]
