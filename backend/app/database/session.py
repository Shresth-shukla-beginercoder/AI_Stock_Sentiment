"""Database session management.

The schema is owned by Alembic only (never ``create_all`` in the app).
This module hands out short-lived sessions bound to the shared engine.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.orm import Session, sessionmaker

from app.database.engine import get_shared_engine


def get_session_factory() -> "sessionmaker[Session]":
    return sessionmaker(bind=get_shared_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: one session per request, closed on exit."""
    factory = get_session_factory()
    with factory() as session:
        yield session


@contextmanager
def session_scope() -> Iterator[Session]:
    """Short-lived session for routes/services that open their own transactions.

    Use this (not ``get_session``, a generator FastAPI dependency) when a
    plain function must read or write the database.
    """
    factory = get_session_factory()
    with factory() as session:
        yield session
