---
name: phase-8-plan
description: Implementation plan for Phase 8: Feature Engineering and ML Prediction.
metadata:
  type: project
---

# Phase 8 Plan: Feature Engineering and ML Prediction

## Objective
Implement feature engineering pipeline (indicators, sentiment features), build experimental next-day-return predictive models (Time-Series Split), and set up the model registry.

## Files to be created/modified
- `backend/app/features/indicators.py`: Technical indicators (Moving Averages, RSI).
- `backend/app/features/build_features.py`: Aggregation of sentiment + price features.
- `backend/app/features/make_target.py`: Next-day-return target construction.
- `backend/app/models/trainer.py`: Time-series walk-forward trainer (TimeSeriesSplit).
- `backend/app/models/registry.py`: Simple model tracking (git commit reference).
- `backend/tests/test_phase8_features_models.py`: Tests for features and trainer.

## Architecture
- **Time-Series Split (Gap=1)**: Ensures no data leakage between train/test folds.
- **Scalers**: Fit inside training folds to prevent look-ahead bias.
- **Registry**: Tracks model metrics and git commit versions.

## Steps
1. Implement technical indicators (`indicators.py`).
2. Build feature aggregation pipeline (`build_features.py`).
3. Construct targets (`make_target.py`).
4. Implement model trainer (`trainer.py`).
5. Implement registry (`registry.py`).
6. Add unit and integration tests.
7. Update documentation (`CLAUDE.md`, `PROGRESS.md`, `VERIFICATION.md`).
