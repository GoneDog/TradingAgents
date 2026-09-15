from pathlib import Path

import pandas as pd

from tradingagents.research.calibration import CalibrationConfig
from tradingagents.research.models import PromotionState
from tradingagents.research.registry import StrategyRegistry
from tradingagents.research.run_calibration import fetch_closes, run_calibration


class FakeTicker:
    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, start, end, auto_adjust=False):
        dates = pd.date_range("2020-01-01", periods=900, freq="D", tz="UTC")
        return pd.DataFrame({"Close": [100 + i * 0.05 for i in range(900)]}, index=dates)


def test_fetch_closes_rejects_rows_at_or_after_cutoff(monkeypatch):
    class BadTicker(FakeTicker):
        def history(self, start, end, auto_adjust=False):
            dates = pd.to_datetime(["2020-01-01", end], utc=True)
            return pd.DataFrame({"Close": [100.0, 101.0]}, index=dates)

    monkeypatch.setattr("tradingagents.research.run_calibration.yf.Ticker", BadTicker)
    try:
        fetch_closes("SPY", start="2020-01-01", as_of="2020-02-01")
        raise AssertionError("expected cutoff violation")
    except ValueError as exc:
        assert "cutoff" in str(exc)


def test_runner_auto_disposes_candidate(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("tradingagents.research.run_calibration.yf.Ticker", FakeTicker)
    registry_path = tmp_path / "registry.db"
    cfg = CalibrationConfig(
        fast_window=5,
        slow_window=20,
        train_bars=120,
        test_bars=60,
        monte_carlo_samples=20,
    )
    rows = run_calibration(
        symbol="SPY",
        start="2020-01-01",
        as_of="2023-01-01",
        registry_path=str(registry_path),
        configs=(cfg,),
    )
    assert len(rows) == 1
    assert rows[0]["state"] in {PromotionState.PAPER.value, PromotionState.REJECTED.value}
    registry = StrategyRegistry(registry_path)
    assert registry.state(rows[0]["strategy_id"]).value == rows[0]["state"]


def test_runner_is_idempotent(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("tradingagents.research.run_calibration.yf.Ticker", FakeTicker)
    registry_path = tmp_path / "registry.db"
    cfg = CalibrationConfig(
        fast_window=5,
        slow_window=20,
        train_bars=120,
        test_bars=60,
        monte_carlo_samples=20,
    )
    kwargs = {
        "symbol": "SPY",
        "start": "2020-01-01",
        "as_of": "2023-01-01",
        "registry_path": str(registry_path),
        "configs": (cfg,),
    }
    first = run_calibration(**kwargs)
    second = run_calibration(**kwargs)
    assert first[0]["strategy_id"] == second[0]["strategy_id"]
    assert first[0]["state"] == second[0]["state"]
