"""Liveness and readiness endpoints.

- GET /api/health  -> application liveness. 200 while the app process runs,
  independent of database state. This is what Docker's healthcheck uses so a
  stopped Postgres does not mark a running backend as "unhealthy".
- GET /api/ready   -> PostgreSQL readiness. 200 when a SELECT 1 succeeds,
  503 when the DB is unreachable. The stop/restart test exercises THIS.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import get_settings
from app.database.engine import get_shared_engine

router = APIRouter(tags=["system"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/health", status_code=status.HTTP_200_OK)
def health() -> dict:
    """Application liveness. No DB check by design."""
    settings = get_settings()
    return {
        "status": "ok",
        "app": "ai-stock-backend",
        "data_mode": settings.data_mode,
        "market_data_provider": settings.market_data_provider or None,
        "timestamp": _utc_now_iso(),
    }


@router.get("/ready", status_code=status.HTTP_200_OK)
def ready() -> JSONResponse:
    """PostgreSQL readiness. 200 reachable, 503 when down."""
    engine = get_shared_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ready", "database": "up", "timestamp": _utc_now_iso()},
        )
    except Exception as exc:  # noqa: BLE001 - readiness must never 500
        # Log only the exception type/message category; never credentials.
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "database": "down",
                "detail": "PostgreSQL is not reachable",
                "timestamp": _utc_now_iso(),
            },
        )
