"""Shared fixtures for the W1–W7 focused tests.

The production schema is created ONLY by Alembic — but tests may create
tables in a disposable in-memory SQLite database (the models are portable:
JSONB degrades to JSON, timestamptz to DATETIME). This fixture is for
query-level unit tests that need real rows; it never touches the Postgres
volume or the Alembic head.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
import app.database.models as models  # noqa: F401 — register all tables


@pytest.fixture()
def sqlite_session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()
