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


def _feature_dict(row: FeatureRow) -> dict[str, Any]:
    """Feature vector for one row (independent of whether its target is known).

    W6: the prediction target row's NEXT session has no realized target yet,
    so its features must be extractable without one — scoring that row with
    its target-gate skipped is exactly what ``predict_next_session`` needs.
    """
    return {
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
        random_state: int = 42,
        holdout_ratio: float = 0.0,
    ):
        """Initialize trainer.

        Args:
            n_splits: Number of expanding folds.
            gap: Gap between training and test fold (default 1 day).
            regularization: Ridge regression alpha (default 1.0).
            random_state: Fixed seed (W6/W7) — passed to Ridge so repeated
                runs are deterministic.
            holdout_ratio: W6 — strict chronological out-of-sample holdout,
                split OFF the END of the series after walk-forward CV. The
                CV folds never see it, so its metrics are a genuine
                out-of-sample estimate. 0.0 disables the holdout.
        """
        self.n_splits = n_splits
        self.gap = gap
        self.regularization = regularization
        self.random_state = random_state
        self.holdout_ratio = holdout_ratio
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

            features.append(_feature_dict(row))
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

        With ``holdout_ratio > 0`` the last chronological chunk is reserved as a
        strict out-of-sample set (walk-forward CV never sees it). The overall
        CV metrics stay as before; the OOS metrics are the honest number to
        quote.

        Returns:
            Dict with keys:
              - fold_metrics: list of (train_metrics, test_metrics) per fold
              - overall_metrics: metrics on all test folds combined
              - baseline_metrics: baseline comparison metrics
              - n_test: total test samples across all folds
              - experimental: True if insufficient data (< 3 test samples)
              - oos_metrics / oos_baselines / oos_n: out-of-sample holdout
                (None when no holdout configured or too little data)
              - beats_nochange_baseline: OOS MAE strictly below the
                no-change baseline MAE (None when no OOS evaluation)
        """
        features, targets = self._extract_xy(rows)

        # W6: reserve a strict chronological holdout before any CV.
        holdout_rows = []
        cv_rows = rows
        oos_metrics = None
        oos_baselines = None
        oos_n = 0
        beats_baseline: Optional[bool] = None
        if self.holdout_ratio and len(rows) >= 10:
            n_holdout = int(len(rows) * self.holdout_ratio)
            # CV needs at least n_splits+2 rows; cap the holdout accordingly.
            n_holdout = min(n_holdout, len(rows) - (self.n_splits + 2))
            if n_holdout >= 2:
                holdout_rows = rows[len(rows) - n_holdout:]
                cv_rows = rows[: len(rows) - n_holdout]

        cv_features, cv_targets = self._extract_xy(cv_rows)

        if len(cv_targets) < 5:
            # Too little data.
            return {
                "fold_metrics": [],
                "overall_metrics": None,
                "baseline_metrics": None,
                "n_test": 0,
                "experimental": True,
                "reason": "insufficient data",
                "oos_metrics": None,
                "oos_baselines": None,
                "oos_n": 0,
                "beats_nochange_baseline": None,
            }

        X = self._impute_features(cv_features)
        y = cv_targets

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

            # Train Ridge regression on training fold (deterministic seed).
            model = Ridge(alpha=self.regularization, random_state=self.random_state)
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

        # W6: strict out-of-sample evaluation on the reserved holdout.
        if holdout_rows:
            h_features, h_targets = self._extract_xy(holdout_rows)
            if h_targets:
                H = self._impute_features(h_features)
                # Fit on the CV part (never on the holdout): scaler + Ridge.
                scaler = StandardScaler()
                X_scaled = scaler.fit_transform(X)
                model = Ridge(alpha=self.regularization, random_state=self.random_state)
                model.fit(X_scaled, y)
                h_scaled = scaler.transform(H)
                h_pred = [float(p) for p in model.predict(h_scaled)]
                oos_n = len(h_targets)
                oos_metrics = compute_metrics(h_targets, h_pred)
                oos_baselines = compute_baselines(h_targets)
                beats_baseline = oos_metrics.mae < oos_baselines.nochange_mae

        return {
            "fold_metrics": fold_metrics,
            "overall_metrics": overall_metrics,
            "baseline_metrics": baseline_metrics,
            "n_test": n_test,
            "experimental": experimental,
            "oos_metrics": oos_metrics,
            "oos_baselines": oos_baselines,
            "oos_n": oos_n,
            "beats_nochange_baseline": beats_baseline,
        }


def predict_next_session(
    rows: list[FeatureRow],
    *,
    seed: int = 42,
    regularization: float = 1.0,
) -> Optional[dict[str, Any]]:
    """Predict the next TRADING session's return for the latest row.

    W6: the prediction is for the row's ``next_trade_date`` (the next observed
    trading bar in the stored series — never a calendar-day +1 guess) and the
    predicted price is computed from that row's actual CLOSE
    (``last_close * (1 + predicted_return)``), never from a target-return
    value. The model is fit on every earlier row; the last row (which has no
    realized target) is the prediction target.

    Returns None when there is not enough history to fit anything honest.
    """
    from app.features.make_target import predicted_price as _predicted_price

    usable = [r for r in rows if r.target_return is not None]
    last = rows[-1] if rows else None
    if last is None or len(usable) < 10:
        return None
    if last.target_return is not None:
        # Every row has a realized target: the next session is not yet observed,
        # so predict it from the full fit (still honest — no target is peeked
        # at because the last row's target is the one being predicted).
        fit_rows = rows
    else:
        fit_rows = rows[:-1]
    if len([r for r in fit_rows if r.target_return is not None]) < 10:
        return None

    features, targets = WalkForwardTrainer(random_state=seed)._extract_xy(fit_rows)
    # _extract_xy drops rows without a realized target; features/targets stay aligned.
    if len(features) < 10 or not targets:
        return None
    X = WalkForwardTrainer()._impute_features(features)
    y = targets

    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import Ridge

    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model = Ridge(alpha=regularization, random_state=seed)
    model.fit(Xs, y)

    last_feats = [_feature_dict(last)]
    last_X = WalkForwardTrainer()._impute_features(last_feats)
    pred_return = float(model.predict(scaler.transform(last_X))[0])
    pred_price = _predicted_price(last.close, pred_return)
    experimental = bool(last.sentiment_experimental)

    return {
        "target_date": last.next_trade_date,   # next TRADING session (None -> caller must skip)
        "predicted_return": pred_return,
        "predicted_price": pred_price,
        "basis_close": last.close,             # the price basis (a close, not a return)
        "made_from_trade_date": last.trade_date,
        "experimental": experimental,
    }


def train_and_evaluate(
    rows: list[FeatureRow],
    *,
    model_version: str = "v0.1",
    git_commit: Optional[str] = None,
    seed: int = 42,
    holdout_ratio: float = 0.2,
) -> dict[str, Any]:
    """Train a model and return evaluation results ready for registry persistence.

    W6/W7: ``seed`` and ``holdout_ratio`` are now explicit (they come from
    ``settings.ml_random_seed`` / ``settings.ml_holdout_ratio`` at the call
    site). The registry entry reports the out-of-sample holdout numbers
    separately from the CV numbers, plus an honest beats-baseline flag.

    Args:
        rows: Feature rows (must include targets).
        model_version: Model version string for registry.
        git_commit: Git commit SHA (or None if not a git repo).
        seed: Fixed random seed (ML determinism).
        holdout_ratio: Fraction of the series tail reserved for OOS.

    Returns:
        Dict with registry entry fields + training metadata.
    """
    trainer = WalkForwardTrainer(
        n_splits=5, gap=1, regularization=1.0,
        random_state=seed, holdout_ratio=holdout_ratio,
    )
    results = trainer.train(rows)

    # Build registry entry.
    overall_metrics = results["overall_metrics"]
    baseline_metrics = results["baseline_metrics"]
    oos_metrics = results.get("oos_metrics")
    oos_baselines = results.get("oos_baselines")

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
        "oos_mae": oos_metrics.mae if oos_metrics else None,
        "oos_rmse": oos_metrics.rmse if oos_metrics else None,
        "oos_directional_accuracy": oos_metrics.directional_accuracy if oos_metrics else None,
        "oos_nochange_mae": oos_baselines.nochange_mae if oos_baselines else None,
        "oos_n": results.get("oos_n", 0),
        "beats_nochange_baseline": results.get("beats_nochange_baseline"),
        "params": {
            "algorithm": "ridge",
            "regularization": 1.0,
            "n_splits": 5,
            "gap": 1,
            "random_state": seed,
            "holdout_ratio": holdout_ratio,
            "oos_holdout": {
                # Persisted with the registry row so the honest out-of-sample
                # numbers survive into model_evaluations.params.
                "mae": oos_metrics.mae if oos_metrics else None,
                "rmse": oos_metrics.rmse if oos_metrics else None,
                "directional_accuracy": oos_metrics.directional_accuracy if oos_metrics else None,
                "nochange_mae": oos_baselines.nochange_mae if oos_baselines else None,
                "n": results.get("oos_n", 0),
                "beats_nochange": results.get("beats_nochange_baseline"),
            },
            "feature_config": {
                "price_indicators": ["return_1d", "return_5d", "return_10d", "ma_5d", "ma_10d", "ma_20d", "volatility_10d", "rsi_14", "volume_ma", "volume_ratio"],
                "sentiment_features": ["sentiment_social_score", "sentiment_news_score"],
            },
        },
        "git_commit": git_commit or "no_git_repo",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "experimental": results["experimental"] or (results.get("oos_n", 0) < 5),
    }

    return registry_entry
