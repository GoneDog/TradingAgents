from __future__ import annotations

import json
from dataclasses import dataclass
from hashlib import sha256

from .backtest import (
    backtest_binary_signal,
    monte_carlo_drawdowns,
    positive_fraction,
    walk_forward_slices,
)


@dataclass(frozen=True)
class CalibrationConfig:
    fast_window: int = 20
    slow_window: int = 100
    round_trip_cost_bps: float = 10.0
    train_bars: int = 504
    test_bars: int = 126
    monte_carlo_samples: int = 1000
    monte_carlo_seed: int = 0

    def validate(self) -> None:
        if self.fast_window <= 1:
            raise ValueError("fast_window must be > 1")
        if self.slow_window <= self.fast_window:
            raise ValueError("slow_window must exceed fast_window")
        if self.train_bars <= self.slow_window:
            raise ValueError("train_bars must exceed slow_window")
        if self.test_bars <= 0:
            raise ValueError("test_bars must be positive")


def dataset_fingerprint(symbol: str, dates: list[str], prices: list[float]) -> str:
    payload = json.dumps(
        {"symbol": symbol.upper(), "dates": dates, "prices": prices},
        separators=(",", ":"),
        sort_keys=True,
    )
    return sha256(payload.encode()).hexdigest()


def sma_signal(prices: list[float], *, fast: int, slow: int) -> list[bool]:
    """Return a causal trend signal using only prices available through each bar."""
    if slow <= fast or fast <= 0:
        raise ValueError("require 0 < fast < slow")
    result = [False] * len(prices)
    fast_sum = 0.0
    slow_sum = 0.0
    for i, price in enumerate(prices):
        fast_sum += price
        slow_sum += price
        if i >= fast:
            fast_sum -= prices[i - fast]
        if i >= slow:
            slow_sum -= prices[i - slow]
        if i + 1 >= slow:
            result[i] = (fast_sum / fast) > (slow_sum / slow)
    return result


def evaluate_sma_calibration(
    prices: list[float],
    *,
    config: CalibrationConfig | None = None,
) -> dict[str, float]:
    """Produce validation metrics for the transparent SMA calibration strategy.

    The strategy is intentionally ordinary. Its job is to verify that the
    factory can measure costs, instability and drawdown correctly, not to serve
    as a presumed source of alpha.
    """
    config = config or CalibrationConfig()
    config.validate()
    signal = sma_signal(prices, fast=config.fast_window, slow=config.slow_window)
    full = backtest_binary_signal(
        prices, signal, round_trip_cost_bps=config.round_trip_cost_bps
    )

    window_returns: list[float] = []
    for _train, test in walk_forward_slices(
        len(prices), train=config.train_bars, test=config.test_bars
    ):
        start = max(0, test.start - config.slow_window)
        sub_prices = prices[start:test.stop]
        sub_signal = sma_signal(
            sub_prices, fast=config.fast_window, slow=config.slow_window
        )
        result = backtest_binary_signal(
            sub_prices, sub_signal, round_trip_cost_bps=config.round_trip_cost_bps
        )
        window_returns.append(result.total_return)

    mc = monte_carlo_drawdowns(
        [t.net_return for t in full.trades],
        samples=config.monte_carlo_samples,
        seed=config.monte_carlo_seed,
    ) if full.trades else []
    mc_sorted = sorted(mc)
    p95 = mc_sorted[min(len(mc_sorted) - 1, int(len(mc_sorted) * 0.95))] if mc_sorted else 0.0

    return {
        "trades": float(len(full.trades)),
        "profit_factor": float(full.profit_factor),
        "max_drawdown": float(full.max_drawdown),
        "cost_share_of_gross_profit": float(full.cost_share_of_gross_profit),
        "walk_forward_windows": float(len(window_returns)),
        "positive_walk_forward_fraction": float(positive_fraction(window_returns)),
        "out_of_sample": 1.0 if window_returns else 0.0,
        "monte_carlo_completed": 1.0 if mc else 0.0,
        "monte_carlo_drawdown_p95": float(p95),
        "total_return": float(full.total_return),
    }
