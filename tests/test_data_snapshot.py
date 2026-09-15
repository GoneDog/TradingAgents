import pytest

from tradingagents.research.data_snapshot import make_price_snapshot


def test_snapshot_rejects_future_rows():
    with pytest.raises(ValueError, match="after as_of"):
        make_price_snapshot(
            "SPY",
            as_of="2026-01-02",
            dates=["2026-01-01", "2026-01-03"],
            closes=[100.0, 101.0],
        )


def test_snapshot_fingerprint_is_stable():
    kwargs = dict(
        symbol="spy",
        as_of="2026-01-02",
        dates=["2026-01-01", "2026-01-02"],
        closes=[100.0, 101.0],
    )
    a = make_price_snapshot(**kwargs)
    b = make_price_snapshot(**kwargs)
    assert a.symbol == "SPY"
    assert a.fingerprint == b.fingerprint
