from tradingagents.research.calibration import (
    CalibrationConfig,
    dataset_fingerprint,
    evaluate_sma_calibration,
    sma_signal,
)


def test_sma_signal_uses_only_past_and_present_prices():
    prices = [100.0 + i for i in range(150)]
    original = sma_signal(prices, fast=5, slow=20)
    mutated = list(prices)
    mutated[-1] = 1_000_000.0
    changed = sma_signal(mutated, fast=5, slow=20)
    assert original[:-1] == changed[:-1]


def test_dataset_fingerprint_changes_with_data():
    dates = ["2026-01-01", "2026-01-02"]
    a = dataset_fingerprint("SPY", dates, [100.0, 101.0])
    b = dataset_fingerprint("SPY", dates, [100.0, 102.0])
    assert a != b


def test_calibration_produces_walk_forward_and_monte_carlo_metrics():
    prices = []
    price = 100.0
    for i in range(900):
        price *= 1.002 if (i // 90) % 2 == 0 else 0.999
        prices.append(price)

    metrics = evaluate_sma_calibration(
        prices,
        config=CalibrationConfig(
            fast_window=10,
            slow_window=40,
            train_bars=252,
            test_bars=63,
            monte_carlo_samples=100,
        ),
    )
    assert metrics["walk_forward_windows"] >= 3
    assert metrics["out_of_sample"] == 1.0
    assert metrics["monte_carlo_completed"] in {0.0, 1.0}
    assert 0.0 <= metrics["positive_walk_forward_fraction"] <= 1.0


def test_bad_config_is_rejected():
    try:
        CalibrationConfig(fast_window=100, slow_window=20).validate()
    except ValueError:
        pass
    else:
        raise AssertionError("invalid fast/slow windows were accepted")
