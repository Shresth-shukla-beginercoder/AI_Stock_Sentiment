"""SQLAlchemy engine (Phase 1: engine only; session + models in Phase 2)."""

from sqlalchemy import create_engine

from app.core.config import get_settings


def get_engine():
    settings = get_settings()
    return create_engine(
        settings.database_url_resolved(),
        pool_pre_ping=True,
        pool_recycle=1800,
        pool_size=5,
        max_overflow=10,
        future=True,
    )


_engine = None


def get_shared_engine():
    """Lazily build and cache a single engine for the process."""
    global _engine
    if _engine is None:
        _engine = get_engine()
    return _engine
