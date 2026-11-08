"""Pydantic v2 request models for Phase 3 endpoints."""

from typing import Literal

from pydantic import BaseModel, Field


class CollectRunRequest(BaseModel):
    """POST /api/collect/run — persist a collection job (executed in Phase 7)."""

    tickers: list[str] = Field(
        ..., min_length=1, max_length=50, description="Tickers to collect, e.g. ['DEMO-HK-001']"
    )
    source: Literal["all", "social", "news"] = Field("all", description="Which collector sources")
    label: str | None = Field(None, max_length=64, description="Optional human-readable label")


class TrainRequest(BaseModel):
    """POST /api/models/train — persist a training job (executed in Phase 8)."""

    tickers: list[str] | None = Field(None, description="Tickers in training scope; all if omitted")
    model_name: str | None = Field(None, max_length=64, description="Model version name")
