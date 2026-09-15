from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .calibration import dataset_fingerprint


@dataclass(frozen=True)
class PriceSnapshot:
    symbol: str
    as_of: str
    dates: tuple[str, ...]
    closes: tuple[float, ...]
    fingerprint: str


def make_price_snapshot(
    symbol: str,
    *,
    as_of: str,
    dates: list[str],
    closes: list[float],
) -> PriceSnapshot:
    """Create an immutable, cutoff-enforced historical price snapshot.

    Any row after ``as_of`` is rejected instead of silently filtered. That makes
    accidental future-data leakage visible at the research boundary.
    """
    if len(dates) != len(closes):
        raise ValueError("dates and closes must have equal length")
    if not dates:
        raise ValueError("snapshot cannot be empty")
    cutoff = date.fromisoformat(as_of)
    parsed = [date.fromisoformat(d) for d in dates]
    if parsed != sorted(parsed):
        raise ValueError("snapshot dates must be sorted ascending")
    if len(set(dates)) != len(dates):
        raise ValueError("snapshot dates must be unique")
    if any(d > cutoff for d in parsed):
        raise ValueError("snapshot contains data after as_of cutoff")
    if any(p <= 0 for p in closes):
        raise ValueError("closing prices must be positive")

    normalized_symbol = symbol.upper()
    fingerprint = dataset_fingerprint(normalized_symbol, dates, closes)
    return PriceSnapshot(
        symbol=normalized_symbol,
        as_of=as_of,
        dates=tuple(dates),
        closes=tuple(float(p) for p in closes),
        fingerprint=fingerprint,
    )
