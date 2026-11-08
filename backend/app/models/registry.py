"""Model registry: persistent tracking of model versions and metrics (Phase 8).

Stores model evaluation results to the database, keyed by model_version.
Never silently replaces a better-performing model; explicit user decision required.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import ModelEvaluation, Prediction
from app.core.logging import get_logger

_log = get_logger("models.registry")


def register_model(
    session: Session,
    model_version: str,
    mae: Optional[float],
    rmse: Optional[float],
    directional_accuracy: Optional[float],
    baseline_nochange_mae: Optional[float],
    baseline_nochange_rmse: Optional[float],
    baseline_nochange_dir_acc: Optional[float],
    baseline_alwaysup_dir_acc: Optional[float],
    n_test: Optional[int],
    params: Optional[dict],
    git_commit: Optional[str],
    *,
    force: bool = False,
) -> ModelEvaluation:
    """Register or update a model in the registry.

    If model_version already exists and force=False, raises ValueError.
    If force=True, overwrites the existing entry (use with caution).

    Args:
        session: Active SQLAlchemy session.
        model_version: Unique model identifier (e.g. "v0.1", "ridge-20261108").
        mae: Mean Absolute Error on test set.
        rmse: Root Mean Squared Error on test set.
        directional_accuracy: Fraction of correct-sign predictions.
        baseline_nochange_mae: No-change baseline MAE.
        baseline_nochange_rmse: No-change baseline RMSE.
        baseline_nochange_dir_acc: No-change baseline directional accuracy.
        baseline_alwaysup_dir_acc: Always-up baseline directional accuracy.
        n_test: Number of test samples evaluated.
        params: Hyperparameter and feature config dict.
        git_commit: Git commit SHA or "no_git_repo" placeholder.
        force: If True, overwrite existing entry (default False).

    Returns:
        ModelEvaluation row from the database.

    Raises:
        ValueError: If model_version exists and force=False.
    """
    # Check if model already exists.
    existing = session.execute(
        select(ModelEvaluation).where(ModelEvaluation.model_version == model_version)
    ).scalar_one_or_none()

    if existing is not None:
        if not force:
            raise ValueError(
                f"Model {model_version!r} already registered. Use force=True to overwrite."
            )
        # Delete the old entry to replace it.
        session.delete(existing)
        session.flush()

    # Create new entry.
    evaluation = ModelEvaluation(
        model_version=model_version,
        mae=mae,
        rmse=rmse,
        directional_accuracy=directional_accuracy,
        baseline_nochange_mae=baseline_nochange_mae,
        baseline_nochange_rmse=baseline_nochange_rmse,
        baseline_nochange_dir_acc=baseline_nochange_dir_acc,
        baseline_alwaysup_dir_acc=baseline_alwaysup_dir_acc,
        n_test=n_test,
        params=params,
        git_commit=git_commit,
        trained_at=datetime.now(timezone.utc),
    )

    session.add(evaluation)
    session.commit()

    _log.info(
        "model registered",
        extra={
            "model_version": model_version,
            "mae": mae,
            "rmse": rmse,
            "dir_acc": directional_accuracy,
            "n_test": n_test,
        },
    )

    return evaluation


def get_model(
    session: Session,
    model_version: str,
) -> Optional[ModelEvaluation]:
    """Retrieve a registered model by version."""
    return session.execute(
        select(ModelEvaluation).where(ModelEvaluation.model_version == model_version)
    ).scalar_one_or_none()


def list_models(session: Session) -> list[ModelEvaluation]:
    """List all registered models, ordered by trained_at descending."""
    return session.execute(
        select(ModelEvaluation).order_by(ModelEvaluation.trained_at.desc())
    ).scalars().all()


def persist_predictions(
    session: Session,
    asset_id: int,
    model_version: str,
    predictions_data: list[dict[str, Any]],
) -> int:
    """Persist model predictions to the predictions table.

    Args:
        session: Active SQLAlchemy session.
        asset_id: Asset ID these predictions are for.
        model_version: Model version that generated the predictions.
        predictions_data: List of dicts with keys:
          - target_date (date): the prediction date
          - predicted_return (float or None)
          - predicted_price (float or None)
          - actual_close (float or None, usually NULL until backfill)
          - experimental (bool)

    Returns:
        Number of rows inserted.
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.database.models import Prediction as PredictionModel
    from datetime import date

    rows_to_insert = []
    for pred in predictions_data:
        rows_to_insert.append({
            "asset_id": asset_id,
            "model_version": model_version,
            "target_date": pred["target_date"],
            "predicted_return": pred.get("predicted_return"),
            "predicted_price": pred.get("predicted_price"),
            "actual_close": pred.get("actual_close"),
            "experimental": pred.get("experimental", False),
            "made_at": datetime.now(timezone.utc),
        })

    if not rows_to_insert:
        return 0

    # Upsert: (asset_id, target_date, model_version) is unique.
    stmt = (
        pg_insert(PredictionModel)
        .values(rows_to_insert)
        .on_conflict_do_update(
            index_elements=["asset_id", "target_date", "model_version"],
            set_={"predicted_return": pg_insert(PredictionModel).excluded.predicted_return,
                  "predicted_price": pg_insert(PredictionModel).excluded.predicted_price}
        )
        .returning(PredictionModel.id)
    )

    result = session.execute(stmt)
    inserted = len(result.fetchall())
    session.commit()

    _log.info(
        "predictions persisted",
        extra={"asset_id": asset_id, "model_version": model_version, "count": inserted},
    )

    return inserted
