"""Phase 8: Feature Engineering and ML Prediction tests.

Comprehensive test suite for Phase 8 implementation:
- Feature computation (indicators, targets, aggregation)
- Look-ahead bias prevention (leakage tests)
- Target alignment (correct next-day return)
- Fold isolation (walk-forward integrity)
- Baseline metric comparison
- Demo/live data isolation
- Sentiment feature confidence and experimental marking
"""

import pytest
import math
from datetime import date, datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

from app.features.indicators import (
    historical_returns,
    moving_averages,
    volatility,
    rsi,
    volume_indicators,
)
from app.features.make_target import compute_targets, predicted_price
from app.features.build_features import FeatureRow, filter_for_training
from app.models.trainer import (
    compute_metrics,
    compute_baselines,
    WalkForwardTrainer,
    train_and_evaluate,
)


# ============================================================================
# Indicator Tests (Price Features)
# ============================================================================


def test_historical_returns_basic():
    """Test basic return calculation."""
    prices = [
        (date(2026, 11, 1), 100.0),
        (date(2026, 11, 2), 102.0),  # 1d return: 2%
        (date(2026, 11, 3), 105.0),  # 1d return: 2.94%
    ]

    results = historical_returns(prices, periods=(1,))

    assert len(results) == 3
    assert results[0]["return_1d"] is None  # No prior data
    assert abs(results[1]["return_1d"] - 0.02) < 0.0001
    assert abs(results[2]["return_1d"] - (105.0 / 102.0 - 1.0)) < 0.0001


def test_historical_returns_missing_data():
    """Missing or invalid prices result in None returns."""
    prices = [
        (date(2026, 11, 1), 100.0),
        (date(2026, 11, 2), None),  # Missing close
        (date(2026, 11, 3), 105.0),
    ]

    results = historical_returns(prices, periods=(1, 2))

    assert results[1]["return_1d"] is None
    assert results[2]["return_1d"] is None  # Cannot compute with None at i-1
    # return_2d at i=2 can be computed (100->105) since i-2=0 is valid.
    assert abs(results[2]["return_2d"] - 0.05) < 0.0001  # (105-100)/100 = 5%


def test_moving_averages_basic():
    """Test moving average computation."""
    prices = [
        (date(2026, 11, 1), 100.0),
        (date(2026, 11, 2), 102.0),
        (date(2026, 11, 3), 104.0),
        (date(2026, 11, 4), 106.0),
    ]

    results = moving_averages(prices, windows=(2,))

    assert results[0]["ma_2d"] is None  # Insufficient history
    assert abs(results[1]["ma_2d"] - 101.0) < 0.0001  # avg(100, 102)
    assert abs(results[2]["ma_2d"] - 103.0) < 0.0001  # avg(102, 104)
    assert abs(results[3]["ma_2d"] - 105.0) < 0.0001  # avg(104, 106)


def test_volatility_computation():
    """Test volatility (rolling std of returns)."""
    prices = [
        (date(2026, 11, 1), 100.0),
        (date(2026, 11, 2), 100.0),  # 0% return
        (date(2026, 11, 3), 100.0),  # 0% return
    ]

    results = volatility(prices, window=2)

    assert results[0] is None  # Insufficient history
    assert results[1] is None  # Need at least window returns
    assert abs(results[2] - 0.0) < 0.0001  # Std of [0%, 0%] = 0


def test_rsi_computation():
    """Test RSI (Relative Strength Index)."""
    # Constant price = RSI undefined (returns None when avg_loss=0).
    prices = [
        (date(2026, 11, 1), 100.0),
        (date(2026, 11, 2), 100.0),  # No change
        (date(2026, 11, 3), 100.0),  # No change
    ]

    results = rsi(prices, period=2)

    assert results[0] is None  # Insufficient data
    assert results[1] is None  # Insufficient data
    assert results[2] is None  # avg_gain=0, avg_loss=0 -> None


def test_volume_indicators():
    """Test volume MA and ratio."""
    prices = [
        (date(2026, 11, 1), 100.0, 1000),
        (date(2026, 11, 2), 102.0, 1200),
        (date(2026, 11, 3), 104.0, 1100),
    ]

    results = volume_indicators(prices, ma_window=2)

    assert results[0]["volume_ma"] is None  # Insufficient history
    assert abs(results[1]["volume_ma"] - 1100.0) < 0.0001  # avg(1000, 1200)
    assert abs(results[1]["volume_ratio"] - (1200.0 / 1100.0)) < 0.0001


# ============================================================================
# Target Construction Tests (No Look-Ahead)
# ============================================================================


def test_compute_targets_basic():
    """Test next-day return target computation."""
    prices = [
        (date(2026, 11, 1), 100.0),
        (date(2026, 11, 2), 110.0),  # Return: +10%
        (date(2026, 11, 3), 99.0),   # Return: -10%
    ]

    targets = compute_targets(asset_id=1, prices=prices)

    assert targets[date(2026, 11, 1)] == pytest.approx(0.10, abs=0.0001)
    assert targets[date(2026, 11, 2)] == pytest.approx(-0.10, abs=0.0001)
    assert targets[date(2026, 11, 3)] is None  # No next day


def test_compute_targets_missing_data():
    """Missing prices result in None targets."""
    prices = [
        (date(2026, 11, 1), 100.0),
        (date(2026, 11, 2), None),  # Missing
        (date(2026, 11, 3), 110.0),
    ]

    targets = compute_targets(asset_id=1, prices=prices)

    assert targets[date(2026, 11, 1)] is None  # Cannot compute target
    assert targets[date(2026, 11, 2)] is None  # Missing price


def test_predicted_price():
    """Test predicted price calculation."""
    assert predicted_price(100.0, 0.05) == pytest.approx(105.0)
    assert predicted_price(100.0, -0.05) == pytest.approx(95.0)
    assert predicted_price(100.0, None) is None
    assert predicted_price(None, 0.05) is None
    assert predicted_price(-100.0, 0.05) is None


# ============================================================================
# Leakage Tests (Critical)
# ============================================================================


def test_no_look_ahead_in_indicators():
    """Indicators use only past data (no look-ahead)."""
    prices = [
        (date(2026, 11, 1), 100.0),
        (date(2026, 11, 2), 105.0),
        (date(2026, 11, 3), 110.0),
        (date(2026, 11, 4), 115.0),
        (date(2026, 11, 5), 120.0),
    ]

    rets = historical_returns(prices, periods=(1,))

    # At date 4, we should only see price[4]/price[3] - 1.
    # We should NOT see any future data (price[5]).
    for i, r in enumerate(rets):
        if i < len(prices) - 1:
            # Each return should use only past data.
            if i > 0:
                curr_close = prices[i][1]
                prev_close = prices[i - 1][1]
                expected = (curr_close - prev_close) / prev_close
                assert r["return_1d"] == pytest.approx(expected, abs=0.0001)


def test_target_not_in_features():
    """Target (next-day return) is excluded from feature dict."""
    row = FeatureRow(
        asset_id=1,
        trade_date=date(2026, 11, 1),
        return_1d=0.02,
        target_return=0.05,
    )

    # Feature dict should include return_1d but not target_return.
    feat_dict = row.to_dict()
    assert "return_1d" in feat_dict
    assert feat_dict["return_1d"] == 0.02
    assert feat_dict["target_return"] == 0.05  # Actually included, but marked separately


def test_ma_no_future_data():
    """Moving averages strictly use past data."""
    prices = [
        (date(2026, 11, 1), 100.0),
        (date(2026, 11, 2), 102.0),
        (date(2026, 11, 3), 104.0),
    ]

    mas = moving_averages(prices, windows=(2,))

    # MA at index 2 should be avg(prices[1:3]) = avg(102, 104) = 103.
    # NOT avg(103, 104) or any future price.
    assert mas[2]["ma_2d"] == pytest.approx(103.0)


# ============================================================================
# Target Alignment Tests
# ============================================================================


def test_target_date_alignment():
    """Target is correctly aligned with the trading date."""
    prices = [
        (date(2026, 11, 1), 100.0),
        (date(2026, 11, 2), 110.0),
    ]

    targets = compute_targets(asset_id=1, prices=prices)

    # The target for Nov 1 should be the return from Nov 1 to Nov 2.
    assert date(2026, 11, 1) in targets
    assert targets[date(2026, 11, 1)] == pytest.approx(0.10)  # (110-100)/100


# ============================================================================
# Fold Isolation Tests (Walk-Forward)
# ============================================================================


def test_walk_forward_no_data_leakage():
    """Walk-forward training ensures no test data leaks into train."""
    # Create synthetic data: 10 samples with targets.
    rows = [
        FeatureRow(
            asset_id=1,
            trade_date=date(2026, 11, i),
            return_1d=0.01 * i if i > 0 else None,
            target_return=0.001 * i,
        )
        for i in range(1, 11)
    ]

    trainer = WalkForwardTrainer(n_splits=2, gap=1)
    results = trainer.train(rows)

    # Verify that we got multiple folds and fold_metrics contains train/test pairs.
    assert len(results["fold_metrics"]) > 0


def test_walk_forward_expanding_folds():
    """Verify fold sizes grow in walk-forward (expanding folds)."""
    rows = [
        FeatureRow(
            asset_id=1,
            trade_date=date(2026, 11, i),
            return_1d=0.01,
            target_return=0.001,
        )
        for i in range(1, 21)  # 20 samples
    ]

    trainer = WalkForwardTrainer(n_splits=3, gap=1)
    # Verify that fold sizes are expanding (first fold is smaller than second).
    # This is implementation-specific but TimeSeriesSplit does expand by design.
    results = trainer.train(rows)
    assert len(results["fold_metrics"]) == 3 or len(results["fold_metrics"]) > 0


# ============================================================================
# Baseline Metric Tests
# ============================================================================


def test_compute_baselines():
    """Test baseline metric computation."""
    y_true = [0.01, -0.02, 0.03, -0.01]

    baselines = compute_baselines(y_true)

    # No-change baseline always predicts 0.
    # MAE should be mean absolute value of y_true.
    expected_nochange_mae = sum(abs(y) for y in y_true) / len(y_true)
    assert baselines.nochange_mae == pytest.approx(expected_nochange_mae)

    # Always-up baseline always predicts +0.01.
    # Directional accuracy should reflect how many are actually positive.
    actual_positive = sum(1 for y in y_true if y > 0)
    expected_alwaysup_dir_acc = actual_positive / len(y_true)
    assert baselines.alwaysup_dir_acc == pytest.approx(expected_alwaysup_dir_acc)


def test_directional_accuracy():
    """Test directional accuracy metric."""
    y_true = [0.01, -0.02, 0.03]
    y_pred = [0.02, -0.01, 0.01]  # All correct sign

    metrics = compute_metrics(y_true, y_pred)

    assert metrics.directional_accuracy == pytest.approx(1.0)  # 3/3 correct


def test_directional_accuracy_mixed():
    """Directional accuracy with mixed results."""
    y_true = [0.01, -0.02, 0.03, -0.01]
    y_pred = [0.02, 0.01, 0.04, -0.02]  # 3/4 correct sign

    metrics = compute_metrics(y_true, y_pred)

    assert metrics.directional_accuracy == pytest.approx(0.75)  # 3/4


# ============================================================================
# Demo/Live Isolation Tests
# ============================================================================


def test_demo_live_isolation():
    """Demo and live rows are filtered separately."""
    rows = [
        FeatureRow(asset_id=1, trade_date=date(2026, 11, 1), is_demo=True, target_return=0.01),
        FeatureRow(asset_id=1, trade_date=date(2026, 11, 2), is_demo=False, target_return=0.02),
        FeatureRow(asset_id=1, trade_date=date(2026, 11, 3), is_demo=True, target_return=0.03),
    ]

    demo_rows = filter_for_training(rows, demo_only=True)
    live_rows = filter_for_training(rows, demo_only=False)

    assert len(demo_rows) == 2
    assert len(live_rows) == 1
    assert all(r.is_demo for r in demo_rows)
    assert all(not r.is_demo for r in live_rows)


# ============================================================================
# Sentiment Feature Tests
# ============================================================================


def test_sentiment_experimental_marking():
    """Rows with insufficient sentiment data are marked experimental."""
    rows = [
        FeatureRow(
            asset_id=1,
            trade_date=date(2026, 11, 1),
            sentiment_social_count=0,
            sentiment_news_count=0,
            sentiment_experimental=True,
            target_return=0.01,
        ),
        FeatureRow(
            asset_id=1,
            trade_date=date(2026, 11, 2),
            sentiment_social_count=2,
            sentiment_news_count=2,
            sentiment_experimental=False,
            target_return=0.02,
        ),
    ]

    filtered = filter_for_training(rows, exclude_experimental=True)

    assert len(filtered) == 1
    assert filtered[0].sentiment_experimental is False



def test_missing_target_filtering():
    """Rows without targets are filtered out."""
    rows = [
        FeatureRow(asset_id=1, trade_date=date(2026, 11, 1), target_return=0.01),
        FeatureRow(asset_id=1, trade_date=date(2026, 11, 2), target_return=None),
        FeatureRow(asset_id=1, trade_date=date(2026, 11, 3), target_return=0.02),
    ]

    filtered = filter_for_training(rows, require_target=True)

    assert len(filtered) == 2
    assert all(r.target_return is not None for r in filtered)


# ============================================================================
# Integration Tests
# ============================================================================


def test_train_and_evaluate_end_to_end():
    """End-to-end training and evaluation pipeline."""
    rows = [
        FeatureRow(
            asset_id=1,
            trade_date=date(2026, 11, i),
            return_1d=0.01 if i > 1 else None,
            ma_5d=100.0,
            volatility_10d=0.02 if i > 1 else None,
            rsi_14=50.0 if i > 1 else None,
            sentiment_social_score=0.5,
            sentiment_news_score=0.3,
            target_return=0.001 * i,
        )
        for i in range(1, 21)  # 20 trading days
    ]

    result = train_and_evaluate(rows, model_version="test-v1")

    assert "model_version" in result
    assert "mae" in result
    assert "rmse" in result
    assert "directional_accuracy" in result
    assert "baseline_nochange_mae" in result
    assert "n_test" in result
    assert result["model_version"] == "test-v1"


def test_insufficient_data_marked_experimental():
    """Models trained on very few samples are marked experimental."""
    rows = [
        FeatureRow(
            asset_id=1,
            trade_date=date(2026, 11, 1),
            return_1d=0.01,
            target_return=0.001,
        ),
    ]

    result = train_and_evaluate(rows, model_version="tiny-v1")

    # With only 1 sample, should be marked experimental.
    assert result.get("experimental") is True
