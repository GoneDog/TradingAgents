import pytest

from tradingagents.research.backtest import (
    backtest_binary_signal,
    monte_carlo_drawdowns,
    walk_forward_slices,
)


def test_signal_executes_next_bar_not_same_bar():
    prices = [100, 200, 220, 110]
    signal = [True, True, False, False]
    result = backtest_binary_signal(prices, signal, round_trip_cost_bps=0)
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.entry_index == 1
    assert trade.exit_index == 3
    assert trade.gross_return == pytest.approx(-0.45)


def test_costs_can_destroy_apparent_edge():
    prices = [100, 101, 100, 101, 100, 101]
    signal = [True, False, True, False, True, False]
    free = backtest_binary_signal(prices, signal, round_trip_cost_bps=0)
    costly = backtest_binary_signal(prices, signal, round_trip_cost_bps=200)
    assert costly.total_return < free.total_return


def test_walk_forward_has_training_before_test():
    windows = list(walk_forward_slices(100, train=40, test=10))
    assert len(windows) == 6
    for train, test in windows:
        assert train.stop == test.start
        assert train.start < train.stop <= test.start < test.stop


def test_monte_carlo_is_reproducible_and_bounded():
    returns = [0.10, -0.05, 0.03, -0.02, 0.08]
    a = monte_carlo_drawdowns(returns, samples=50, seed=42)
    b = monte_carlo_drawdowns(returns, samples=50, seed=42)
    assert a == b
    assert all(0 <= d <= 1 for d in a)
