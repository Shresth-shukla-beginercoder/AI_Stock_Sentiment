"""Declarative Base + shared column types.

Rules (CLAUDE.md):
- UTC everywhere: the ``utc_now`` default and ``UTCDateTime`` type reject naive
  datetimes at the model layer so naive timestamps never reach the database.
- No data means None/NULL, never 0 (see nullable fields in models.py).
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, TypeDecorator, text
from sqlalchemy.orm import DeclarativeBase


def utc_now() -> datetime:
    """Default value for created_at / updated_at / made_at columns."""
    return datetime.now(timezone.utc)


def _server_ts() -> str:
    """DB-side UTC default so NOT NULL timestamp columns are safe under raw SQL.

    Postgres ``now()`` returns timestamptz (transaction time, UTC), satisfying
    the 'UTC everywhere' rule even when the ORM default is bypassed.
    """
    return text("now()")


class Base(DeclarativeBase):
    """Base for all ORM models. Alembic autogenerate uses ``Base.metadata``."""


class UTCDateTime(TypeDecorator):
    """timestamptz on Postgres; enforces tz-aware UTC at the Python boundary.

    Accepts aware datetimes (normalised to UTC) and raises on naive input.
    ``None`` passes through (missing data stays NULL).
    """

    impl = DateTime(timezone=True)
    cache_ok = True
    cache_key = "utcdatetime"

    def process_bind_param(self, value: Optional[datetime], dialect) -> Optional[datetime]:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError(
                f"naive datetime rejected: {value.isoformat()} — all timestamps must be UTC-aware"
            )
        return value.astimezone(timezone.utc)
