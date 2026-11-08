"""Time-series model trainer with walk-forward validation (Phase 8).

Trains next-day-return prediction models using expanding walk-forward folds
(TimeSeriesSplit, gap=1). Per-fold scaler fitting prevents look-ahead bias.
Compares models against zero-return and always-up baselines. Persists metrics
and model version info to the registry.

No model artifacts are stored (this is a feature/metrics pipeline); final model
training is Phase 9. Here we verify the pipeline end-to-end.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, date
from typing import Optional, Any
import math

from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error

from app.features.build_features import FeatureRow


@dataclass
class ModelMetrics:
    """Evaluation metrics for one fold or the full model."""

    mae: float
    rmse: float
    directional_accuracy: float  # fraction of predictions with correct sign


@dataclass
class BaselineMetrics:
    """Baseline (no-change, always-up) metrics."""

    nochange_mae: float
    nochange_rmse: float
    nochange_dir_acc: float
    alwaysup_dir_acc: float


def compute_metrics(
    y_true: list[float],
    y_pred: list[float],
) -> ModelMetrics:
    """Compute MAE, RMSE, and directional accuracy.

    Directional accuracy = fraction where sign(y_pred) == sign(y_true).
    Returns None metrics if y_true is empty or all same sign.
    """
    if not y_true:
        return ModelMetrics(mae=0.0, rmse=0.0, directional_accuracy=0.0)

    mae = mean_absolute_error(y_true, y_pred)
    rmse = math.sqrt(mean_squared_error(y_true, y_pred))

    # Directional accuracy: how many predictions got the sign right?
    correct_direction = sum(
        1 for yt, yp in zip(y_true, y_pred)
        if (yt > 0 and yp > 0) or (yt <= 0 and yp <= 0)
    )
    dir_acc = correct_direction / len(y_true) if y_true else 0.0

    return ModelMetrics(mae=mae, rmse=rmse, directional_accuracy=dir_acc)


def compute_baselines(
    y_true: list[float],
) -> BaselineMetrics:
    """Compute baseline (no-change, always-up) metrics.

    no-change: always predict 0 (no movement).
    always-up: always predict +1% (or a small positive return).
    """
    if not y_true:
        return BaselineMetrics(
            nochange_mae=0.0,
            nochange_rmse=0.0,
            nochange_dir_acc=0.0,
            alwaysup_dir_acc=0.0,
        )

    # Baseline 1: no-change (always predict 0).
    nochange_pred = [0.0] * len(y_true)
    nochange_metrics = compute_metrics(y_true, nochange_pred)

    # Baseline 2: always-up (always predict +0.01 = +1%).
    alwaysup_pred = [0.01] * len(y_true)
    alwaysup_metrics = compute_metrics(y_true, alwaysup_pred)

    return BaselineMetrics(
        nochange_mae=nochange_metrics.mae,
        nochange_rmse=nochange_metrics.rmse,
        nochange_dir_acc=nochange_metrics.directional_accuracy,
        alwaysup_dir_acc=alwaysup_metrics.directional_accuracy,
    )


class WalkForwardTrainer:
    """Walk-forward trainer with expanding folds and per-fold scaling.

    TimeSeriesSplit with gap=1 ensures no data leakage. Scalers are fit
    separately on each training fold to prevent look-ahead bias.
    """

    def __init__(
        self,
        n_splits: int = 5,
        gap: int = 1,
        regularization: float = 1.0,
    ):
        """Initialize trainer.

        Args:
            n_splits: Number of expanding folds.
            gap: Gap between training and test fold (default 1 day).
            regularization: Ridge regression alpha (default 1.0).
        """
        self.n_splits = n_splits
        self.gap = gap
        self.regularization = regularization
        self.tscv = TimeSeriesSplit(n_splits=n_splits, gap=gap)

    def _extract_xy(
        self,
        rows: list[FeatureRow],
    ) -> tuple[list[dict[str, Any]], list[float]]:
        """Extract feature dicts and targets from rows.

        Returns:
            (features_list, targets_list) where features are dicts and
            targets are the next-day returns.
        """
        features = []
        targets = []

        for row in rows:
            if row.target_return is None:
                continue

            feat_dict = {
                "return_1d": row.return_1d,
                "return_5d": row.return_5d,
                "return_10d": row.return_10d,
                "ma_5d": row.ma_5d,
                "ma_10d": row.ma_10d,
                "ma_20d": row.ma_20d,
                "volatility_10d": row.volatility_10d,
                "rsi_14": row.rsi_14,
                "volume_ma": row.volume_ma,
                "volume_ratio": row.volume_ratio,
                "sentiment_social_score": row.sentiment_social_score,
                "sentiment_news_score": row.sentiment_news_score,
            }
            features.append(feat_dict)
            targets.append(row.target_return)

        return features, targets

    def _impute_features(
        self,
        features: list[dict[str, Any]],
    ) -> list[list[float]]:
        """Convert dict features to numeric arrays, imputing missing values.

        Missing values are imputed as 0.0 (honest: the model learns to
        handle missing data). Feature order is deterministic.
        """
        if not features:
            return []

        feature_names = sorted(features[0].keys())
        arrays = []

        for feat_dict in features:
            row = [feat_dict.get(name, 0.0) or 0.0 for name in feature_names]
            arrays.append(row)

        return arrays

    def train(
        self,
        rows: list[FeatureRow],
    ) -> dict[str, Any]:
        """Run walk-forward training and evaluation.

        Returns:
            Dict with keys:
              - fold_metrics: list of (train_metrics, test_metrics) per fold
              - overall_metrics: metrics on all test folds combined
              - baseline_metrics: baseline comparison metrics
              - n_test: total test samples across all folds
              - experimental: True if insufficient data (< 3 test samples)
        """
        features, targets = self._extract_xy(rows)

        if len(targets) < 5:
            # Too little data.
            return {
                "fold_metrics": [],
                "overall_metrics": None,
                "baseline_metrics": None,
                "n_test": 0,
                "experimental": True,
                "reason": "insufficient data",
            }

        X = self._impute_features(features)
        y = targets

        # Walk-forward CV: expanding folds.
        all_test_preds = []
        all_test_targets = []
        fold_metrics = []

        for train_idx, test_idx in self.tscv.split(X):
            if len(test_idx) == 0:
                continue

            # Extract train/test
            X_train = [X[i] for i in train_idx]
            y_train = [y[i] for i in train_idx]
            X_test = [X[i] for i in test_idx]
            y_test = [y[i] for i in test_idx]

            # Fit scaler on training fold only.
            scaler = StandardScaler()
            X_train_scaled = scaler.fit_transform(X_train)
            X_test_scaled = scaler.transform(X_test)

            # Train Ridge regression on training fold.
            model = Ridge(alpha=self.regularization)
            model.fit(X_train_scaled, y_train)

            # Predict on test fold.
            y_train_pred = model.predict(X_train_scaled)
            y_test_pred = model.predict(X_test_scaled)

            # Compute metrics for this fold.
            train_metrics = compute_metrics(y_train, y_train_pred)
            test_metrics = compute_metrics(y_test, y_test_pred)
            fold_metrics.append((train_metrics, test_metrics))

            # Accumulate for overall metrics.
            all_test_preds.extend(y_test_pred)
            all_test_targets.extend(y_test)

        # Overall metrics on all test predictions.
        overall_metrics = compute_metrics(all_test_targets, all_test_preds) if all_test_preds else None
        baseline_metrics = compute_baselines(all_test_targets) if all_test_targets else None

        n_test = len(all_test_targets)
        experimental = n_test < 3  # Mark as experimental if very few test samples.

        return {
            "fold_metrics": fold_metrics,
            "overall_metrics": overall_metrics,
            "baseline_metrics": baseline_metrics,
            "n_test": n_test,
            "experimental": experimental,
        }


def train_and_evaluate(
    rows: list[FeatureRow],
    *,
    model_version: str = "v0.1",
    git_commit: Optional[str] = None,
) -> dict[str, Any]:
    """Train a model and return evaluation results ready for registry persistence.

    Args:
        rows: Feature rows (must include targets).
        model_version: Model version string for registry.
        git_commit: Git commit SHA (or None if not a git repo).

    Returns:
        Dict with registry entry fields + training metadata.
    """
    trainer = WalkForwardTrainer(n_splits=5, gap=1, regularization=1.0)
    results = trainer.train(rows)

    # Build registry entry.
    overall_metrics = results["overall_metrics"]
    baseline_metrics = results["baseline_metrics"]

    registry_entry = {
        "model_version": model_version,
        "mae": overall_metrics.mae if overall_metrics else None,
        "rmse": overall_metrics.rmse if overall_metrics else None,
        "directional_accuracy": overall_metrics.directional_accuracy if overall_metrics else None,
        "baseline_nochange_mae": baseline_metrics.nochange_mae if baseline_metrics else None,
        "baseline_nochange_rmse": baseline_metrics.nochange_rmse if baseline_metrics else None,
        "baseline_nochange_dir_acc": baseline_metrics.nochange_dir_acc if baseline_metrics else None,
        "baseline_alwaysup_dir_acc": baseline_metrics.alwaysup_dir_acc if baseline_metrics else None,
        "n_test": results["n_test"],
        "params": {
            "algorithm": "ridge",
            "regularization": 1.0,
            "n_splits": 5,
            "gap": 1,
            "feature_config": {
                "price_indicators": ["return_1d", "return_5d", "return_10d", "ma_5d", "ma_10d", "ma_20d", "volatility_10d", "rsi_14", "volume_ma", "volume_ratio"],
                "sentiment_features": ["sentiment_social_score", "sentiment_news_score"],
            },
        },
        "git_commit": git_commit or "no_git_repo",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "experimental": results["experimental"],
    }

    return registry_entry
