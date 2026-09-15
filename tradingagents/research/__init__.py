"""Autonomous strategy research and validation primitives."""

from .backtest import (
    BacktestResult,
    Trade,
    backtest_binary_signal,
    monte_carlo_drawdowns,
    positive_fraction,
    walk_forward_slices,
)
from .models import PromotionState, StrategyCandidate, ValidationResult
from .registry import StrategyRegistry
from .validation import ValidationPolicy, validate_candidate

__all__ = [
    "BacktestResult",
    "PromotionState",
    "StrategyCandidate",
    "StrategyRegistry",
    "Trade",
    "ValidationPolicy",
    "ValidationResult",
    "backtest_binary_signal",
    "monte_carlo_drawdowns",
    "positive_fraction",
    "validate_candidate",
    "walk_forward_slices",
]
