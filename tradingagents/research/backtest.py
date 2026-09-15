from __future__ import annotations

from dataclasses import dataclass
import math
import random
from statistics import mean


@dataclass(frozen=True)
class Trade:
    entry_index: int
    exit_index: int
    gross_return: float
    net_return: float


@dataclass(frozen=True)
class BacktestResult:
    trades: tuple[Trade, ...]
    total_return: float
    max_drawdown: float
    profit_factor: float
    cost_share_of_gross_profit: float


def _max_drawdown(returns: list[float]) -> float:
    equity = 1.0
    peak = 1.0
    worst = 0.0
    for r in returns:
        equity *= 1.0 + r
        peak = max(peak, equity)
        if peak:
            worst = max(worst, (peak - equity) / peak)
    return worst


def backtest_binary_signal(
    prices: list[float],
    signal: list[bool],
    *,
    round_trip_cost_bps: float = 10.0,
) -> BacktestResult:
    """Long/cash reference engine for falsifying generated hypotheses.

    Signals are decisions known at close i and execute on the next available
    price, preventing same-bar look-ahead. A trade closes when the signal turns
    false. This deliberately small engine is independently testable; richer
    Backtrader strategies can later implement the same contract.
    """
    if len(prices) != len(signal):
        raise ValueError("prices and signal must have equal length")
    if len(prices) < 3:
        return BacktestResult((), 0.0, 0.0, 0.0, 0.0)
    if any(p <= 0 or not math.isfinite(p) for p in prices):
        raise ValueError("prices must be finite and positive")

    cost = round_trip_cost_bps / 10_000.0
    trades: list[Trade] = []
    entry: int | None = None
    for decision_i in range(len(prices) - 1):
        execute_i = decision_i + 1
        desired_long = bool(signal[decision_i])
        if desired_long and entry is None:
            entry = execute_i
        elif not desired_long and entry is not None and execute_i > entry:
            gross = prices[execute_i] / prices[entry] - 1.0
            trades.append(Trade(entry, execute_i, gross, gross - cost))
            entry = None
    if entry is not None and entry < len(prices) - 1:
        exit_i = len(prices) - 1
        gross = prices[exit_i] / prices[entry] - 1.0
        trades.append(Trade(entry, exit_i, gross, gross - cost))

    nets = [t.net_return for t in trades]
    total = math.prod(1.0 + r for r in nets) - 1.0 if nets else 0.0
    wins = sum(max(t.net_return, 0.0) for t in trades)
    losses = abs(sum(min(t.net_return, 0.0) for t in trades))
    pf = wins / losses if losses else (float("inf") if wins else 0.0)
    gross_profit = sum(max(t.gross_return, 0.0) for t in trades)
    costs = cost * len(trades)
    cost_share = costs / gross_profit if gross_profit else (1.0 if costs else 0.0)
    return BacktestResult(tuple(trades), total, _max_drawdown(nets), pf, cost_share)


def walk_forward_slices(length: int, *, train: int, test: int, step: int | None = None):
    """Yield non-overlapping test windows following each training window."""
    if min(length, train, test) <= 0:
        raise ValueError("length, train and test must be positive")
    step = step or test
    start = 0
    while start + train + test <= length:
        yield slice(start, start + train), slice(start + train, start + train + test)
        start += step


def monte_carlo_drawdowns(
    trade_returns: list[float], *, samples: int = 1000, seed: int = 0
) -> list[float]:
    """Shuffle realized trades to expose sequence-of-returns drawdown risk."""
    if samples <= 0:
        raise ValueError("samples must be positive")
    rng = random.Random(seed)
    results = []
    for _ in range(samples):
        shuffled = list(trade_returns)
        rng.shuffle(shuffled)
        results.append(_max_drawdown(shuffled))
    return results


def positive_fraction(values: list[float]) -> float:
    return mean(v > 0 for v in values) if values else 0.0
