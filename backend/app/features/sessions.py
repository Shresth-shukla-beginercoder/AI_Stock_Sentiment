"""Exchange-local session dates (W2).

A trading *session* is a local calendar day on the exchange's own clock:

- HKEX sessions are ``Asia/Hong_Kong`` (UTC+8)
- KRX sessions are ``Asia/Seoul`` (UTC+9)

Posts and news carry UTC ``timestamptz`` timestamps. Belonging to a session is
therefore decided in the exchange's local timezone, not UTC: an article
published at 2026-11-10 15:30 UTC is part of the *KRX* 2026-11-11 session
(00:30 KST), but of the *HKEX* 2026-11-10 session (23:30 HKT).

Both the ``score:sentiment`` job filter and per-asset sentiment aggregation
must use these session boundaries, and the mapping is transparent (this
module), never a magic offset scattered through queries.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

#: Exchange -> IANA timezone for local session dates.
EXCHANGE_TZ: dict[str, str] = {
    "HKEX": "Asia/Hong_Kong",   # UTC+8
    "KRX": "Asia/Seoul",        # UTC+9
}

_FALLBACK_TZ = "UTC"


def exchange_tz_name(exchange: Optional[str]) -> str:
    """IANA timezone name for an exchange; unknown exchanges fall back to UTC.

    Falling back to UTC keeps the module total (never raises) and honest:
    an unlisted exchange is simply treated as UTC sessions, which is what the
    pre-W2 behaviour was.
    """
    if not exchange:
        return _FALLBACK_TZ
    return EXCHANGE_TZ.get(exchange.upper(), _FALLBACK_TZ)


def local_session_date(utc_dt: datetime, exchange: Optional[str]) -> date:
    """The exchange-local calendar date a UTC timestamp belongs to.

    Naive datetimes are rejected: session mapping is only meaningful in UTC.
    """
    if utc_dt.tzinfo is None:
        raise ValueError("local_session_date requires an aware UTC datetime")
    tz = ZoneInfo(exchange_tz_name(exchange))
    return utc_dt.astimezone(tz).date()


def session_utc_range(session_date: date, exchange: Optional[str]) -> Tuple[datetime, datetime]:
    """Half-open UTC range [start, end) that exactly covers one local session.

    ``start`` is 00:00 local converted to UTC; ``end`` is the following local
    midnight. Filtering ``ts >= start AND ts < end`` selects exactly the rows
    that belong to the session, with no off-by-one at the boundary.
    """
    tz = ZoneInfo(exchange_tz_name(exchange))
    start_local = datetime(session_date.year, session_date.month, session_date.day,
                           tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(ZoneInfo("UTC")), end_local.astimezone(ZoneInfo("UTC"))


def belongs_to_session(utc_dt: datetime, session_date: date,
                       exchange: Optional[str]) -> bool:
    """True when an aware UTC timestamp falls inside the given local session."""
    start, end = session_utc_range(session_date, exchange)
    return start <= utc_dt < end
