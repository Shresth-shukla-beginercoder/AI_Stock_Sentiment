"""W2: exchange-local session date mapping (HK UTC+8, KR UTC+9) boundary tests."""

from datetime import date, datetime, timezone
import pytest

from app.features.sessions import (
    belongs_to_session,
    exchange_tz_name,
    local_session_date,
    session_utc_range,
)

UTC = timezone.utc


def test_exchange_tz_names():
    assert exchange_tz_name("HKEX") == "Asia/Hong_Kong"
    assert exchange_tz_name("KRX") == "Asia/Seoul"
    # case-insensitive
    assert exchange_tz_name("krx") == "Asia/Seoul"
    # unknown -> UTC, never raises
    assert exchange_tz_name("NASDAQ") == "UTC"
    assert exchange_tz_name(None) == "UTC"


def test_local_session_date_same_utc_instant_differs_by_exchange():
    """2026-11-10 15:30 UTC = 23:30 HKT on 11-10 but 00:30 KST on 11-11."""
    ts = datetime(2026, 11, 10, 15, 30, tzinfo=UTC)
    assert local_session_date(ts, "HKEX") == date(2026, 11, 10)
    assert local_session_date(ts, "KRX") == date(2026, 11, 11)


def test_hkex_midnight_boundary():
    """15:59 UTC is still 11-10 HKT; 16:00 UTC is 11-11 HKT (00:00)."""
    before = datetime(2026, 11, 10, 15, 59, 59, tzinfo=UTC)
    at = datetime(2026, 11, 10, 16, 0, 0, tzinfo=UTC)
    assert local_session_date(before, "HKEX") == date(2026, 11, 10)
    assert local_session_date(at, "HKEX") == date(2026, 11, 11)


def test_krx_midnight_boundary():
    """14:59 UTC is still 11-10 KST; 15:00 UTC is 11-11 KST (00:00)."""
    before = datetime(2026, 11, 10, 14, 59, 59, tzinfo=UTC)
    at = datetime(2026, 11, 10, 15, 0, 0, tzinfo=UTC)
    assert local_session_date(before, "KRX") == date(2026, 11, 10)
    assert local_session_date(at, "KRX") == date(2026, 11, 11)


def test_session_utc_range_half_open():
    """KRX 11-10 session = [11-09 15:00 UTC, 11-10 15:00 UTC)."""
    start, end = session_utc_range(date(2026, 11, 10), "KRX")
    assert start == datetime(2026, 11, 9, 15, 0, tzinfo=UTC)
    assert end == datetime(2026, 11, 10, 15, 0, tzinfo=UTC)
    # HKEX 11-10 session = [11-09 16:00 UTC, 11-10 16:00 UTC).
    start, end = session_utc_range(date(2026, 11, 10), "HKEX")
    assert start == datetime(2026, 11, 9, 16, 0, tzinfo=UTC)
    assert end == datetime(2026, 11, 10, 16, 0, tzinfo=UTC)


def test_belongs_to_session_boundaries():
    ts_in = datetime(2026, 11, 10, 15, 30, tzinfo=UTC)
    # KRX: belongs to 11-11 session (00:30 KST), not 11-10.
    assert belongs_to_session(ts_in, date(2026, 11, 11), "KRX") is True
    assert belongs_to_session(ts_in, date(2026, 11, 10), "KRX") is False
    # HKEX: belongs to 11-10 session (23:30 HKT), not 11-11.
    assert belongs_to_session(ts_in, date(2026, 11, 10), "HKEX") is True
    assert belongs_to_session(ts_in, date(2026, 11, 11), "HKEX") is False


def test_session_range_ends_exclusive():
    """A timestamp exactly at the session end belongs to the NEXT session."""
    krx_start, krx_end = session_utc_range(date(2026, 11, 10), "KRX")
    assert belongs_to_session(krx_start, date(2026, 11, 10), "KRX") is True
    assert belongs_to_session(krx_end, date(2026, 11, 10), "KRX") is False
    assert belongs_to_session(krx_end, date(2026, 11, 11), "KRX") is True


def test_unknown_exchange_falls_back_to_utc_session():
    start, end = session_utc_range(date(2026, 11, 10), "NASDAQ")
    assert start == datetime(2026, 11, 10, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 11, 11, 0, 0, tzinfo=UTC)


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        local_session_date(datetime(2026, 11, 10, 15, 30), "HKEX")
