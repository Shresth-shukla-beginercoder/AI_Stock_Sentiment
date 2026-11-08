"""Consistent API response envelope (CLAUDE.md: one error envelope).

Success:  {"success": true,  "data": ..., "meta": {...}, "data_mode": ..., "as_of": ISO-8601 UTC}
Error:    {"success": false, "error": {"code","message","details"?}, "data_mode": ..., "as_of": ...}

Rules:
- as_of is always UTC ISO-8601.
- data_mode is explicit ("demo"/"live"), never inferred.
- APIError is raised by routers and normalised into the envelope by errors.py.
"""

from datetime import date, datetime, timezone
from typing import Annotated, Any

from fastapi import Path as FastAPIPath
from pydantic import AfterValidator, Field

__all__ = [
    "APIError",
    "as_of_now",
    "iso",
    "ok",
    "paginated_meta",
    "Ticker",
    "AwareDT",
    "AwareDate",
]


def as_of_now() -> str:
    """Current UTC time, ISO-8601."""
    return datetime.now(timezone.utc).isoformat()


def iso(value: datetime | date | None) -> str | None:
    """Serialise a value to ISO-8601; None stays None (no fabricated fallbacks)."""
    return value.isoformat() if value is not None else None


def ok(data: Any, *, meta: dict | None = None, data_mode: str = "demo") -> dict:
    """Success envelope. Every data response carries data_mode + as_of."""
    return {
        "success": True,
        "data": data,
        "meta": meta or {},
        "data_mode": data_mode,
        "as_of": as_of_now(),
    }


def paginated_meta(
    *,
    limit: int,
    offset: int,
    total: int,
    state: str,
    source: str,
    note: str | None = None,
) -> dict:
    """Standard list-endpoint meta block."""
    meta: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
        "total": total,
        "has_more": offset + limit < total,
        "state": state,  # "ok" | "no_data"
        "source": source,  # "demo-synthetic" | "database"
    }
    if note:
        meta["note"] = note
    return meta


class APIError(Exception):
    """Routers raise this; errors.py converts it to the error envelope."""

    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        super().__init__(f"{status_code} {code}: {message}")


# --- reusable validated parameter types ---------------------------------------

_TICKER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9.\-]{0,31}$"


def _require_aware(value: Any) -> Any:
    if isinstance(value, datetime) and value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware (UTC); naive values are rejected")
    return value


AwareDT = Annotated[datetime | None, AfterValidator(_require_aware)]
AwareDate = Annotated[date | None, Field(default=None, description="UTC calendar date")]

Ticker = Annotated[
    str,
    FastAPIPath(
        min_length=1,
        max_length=32,
        pattern=_TICKER_PATTERN,
        description=(
            "Ticker, e.g. 0700 or 005930.KS. In demo mode the universe is the synthetic "
            "identifiers DEMO-HK-001 / DEMO-KR-001 (never real tickers). Invalid shape -> 422, "
            "unknown ticker -> 404."
        ),
    ),
]
