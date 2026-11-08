"""FastAPI application factory.

Phase 1: liveness/readiness. Phase 3: full API contract + demo-data layer.
- App factory with lifespan + CORS.
- Liveness: GET /api/health (independent of DB)
- Readiness: GET /api/ready (PostgreSQL connectivity)
- Business routes: assets, posts, news, prices, sentiment, predictions,
  reports, models, jobs, collection/training (see app.api.routes).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_exception_handlers
from app.api.health import router as health_router
from app.api.routes import router as routes_router
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
            "experimental next-day return model. Not financial advice. "
            "Responses carry data_mode (demo/live) and as_of (UTC ISO-8601)."
        ),
        lifespan=lifespan,
        openapi_url="/api/openapi.json",
        docs_url="/docs",
        redoc_url=None,
    )

    # CORS: explicit origin list from config, never "*".
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    install_exception_handlers(app)

    app.include_router(health_router, prefix="/api")
    app.include_router(routes_router, prefix="/api")

    return app


app = create_app()
