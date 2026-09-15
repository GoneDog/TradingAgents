from __future__ import annotations

from dataclasses import asdict
from datetime import date
import json

import yfinance as yf

from .calibration import CalibrationConfig, dataset_fingerprint, evaluate_sma_calibration
from .models import PromotionState, StrategyCandidate
from .registry import StrategyRegistry
from .validation import validate_candidate


def fetch_closes(symbol: str, *, start: str, as_of: str) -> tuple[list[str], list[float]]:
    """Fetch closes strictly before the exclusive as_of cutoff."""
    cutoff = date.fromisoformat(as_of)
    frame = yf.Ticker(symbol).history(start=start, end=cutoff.isoformat(), auto_adjust=False)
    if frame.empty:
        raise ValueError(f"no historical data for {symbol}")
    dates = [idx.date().isoformat() for idx in frame.index]
    if any(date.fromisoformat(d) >= cutoff for d in dates):
        raise ValueError("dataset violates point-in-time cutoff")
    closes = [float(v) for v in frame["Close"].tolist()]
    if len(closes) < 3:
        raise ValueError("insufficient historical observations")
    return dates, closes


def run_calibration(
    *,
    symbol: str,
    start: str,
    as_of: str,
    registry_path: str,
    configs: tuple[CalibrationConfig, ...] | None = None,
) -> list[dict]:
    """Run fixed calibration candidates and automatically reject/promote them."""
    dates, closes = fetch_closes(symbol, start=start, as_of=as_of)
    fingerprint = dataset_fingerprint(symbol, dates, closes)
    registry = StrategyRegistry(registry_path)
    configs = configs or (
        CalibrationConfig(fast_window=20, slow_window=100),
        CalibrationConfig(fast_window=50, slow_window=200),
    )
    output: list[dict] = []

    for cfg in configs:
        candidate = StrategyCandidate(
            name=f"sma-{cfg.fast_window}-{cfg.slow_window}-{symbol.upper()}",
            hypothesis=(
                f"{symbol.upper()} trend persistence is exploitable when "
                f"SMA({cfg.fast_window}) exceeds SMA({cfg.slow_window})"
            ),
            strategy_spec={"family": "sma_trend", **asdict(cfg), "symbol": symbol.upper()},
            data_version=fingerprint,
            generator="calibration-fixed",
            created_at=f"{as_of}T00:00:00Z",
            tags=("calibration", "trend", "long_cash"),
        )
        registry.register(candidate)
        metrics = evaluate_sma_calibration(closes, config=cfg)
        result = validate_candidate(
            candidate,
            validator="deterministic-calibration-checker",
            metrics=metrics,
        )
        registry.record_validation(result)

        current = registry.state(candidate.strategy_id)
        if current == PromotionState.CANDIDATE:
            target = PromotionState.PAPER if result.passed else PromotionState.REJECTED
            registry.transition(
                candidate.strategy_id,
                target,
                actor="deterministic-promotion-gate",
                reason="passed" if result.passed else ",".join(result.reasons),
            )

        output.append(
            {
                "strategy_id": candidate.strategy_id,
                "name": candidate.name,
                "dataset_fingerprint": fingerprint,
                "state": registry.state(candidate.strategy_id).value,
                "metrics": metrics,
                "reasons": list(result.reasons),
            }
        )
    return output


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run unattended TradingAgents calibration")
    parser.add_argument("symbol")
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--as-of", required=True, help="exclusive YYYY-MM-DD historical cutoff")
    parser.add_argument("--registry", default="research_registry.db")
    args = parser.parse_args()
    print(json.dumps(run_calibration(
        symbol=args.symbol,
        start=args.start,
        as_of=args.as_of,
        registry_path=args.registry,
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
