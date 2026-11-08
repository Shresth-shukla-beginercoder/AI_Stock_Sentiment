"""FastAPI application factory.

Phase 1 scope:
- App factory with lifespan + CORS.
- Liveness: GET /api/health
- Readiness: GET /api/ready (PostgreSQL connectivity)
Everything else (business routes) is added in Phase 3+.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging

log = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging()
    log.info(
        "backend starting | data_mode=%s (explicit setting, never inferred) | "
        "missing_credentials=%s | configured_credentials=%s | market_data_provider=%s",
        settings.data_mode,
        ",".join(settings.missing_credentials()) or "none",
        ",".join(settings.configured_credentials()) or "none",
        settings.market_data_provider or "(unselected)",
    )
    # Intentionally no secret values logged above (names only).
    yield
    log.info("backend shutting down")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AI Stock Sentiment Agent",
        version="1.0.0",
        description=(
            "Research platform: social + news sentiment for HKEX/KRX stocks, "
            "experimental next-day return model. Not financial advice."
        ),
        lifespan=lifespan,
    )

    # CORS: explicit origin list from config, never "*".
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(health_router, prefix="/api")

    return app


app = create_app()
