"""W4: per-ticker support/resistance from actual stored price bars.

Methodology (transparent/reproducible): support = min(low), resistance =
max(high) over the most recent N stored sessions. Insufficient history is
reported (data_sufficient=False, levels NULL), never fabricated.
"""

from datetime import date, timedelta

from app.database.models import Asset, MarketPrice
from app.features.support_resistance import levels_to_dict, support_resistance


def _seed(session, asset_id: int, n_sessions: int, *, provider: str = "twelve_data"):
    """Insert n_sessions bars around 2026-11-10 with deterministic OHLC."""
    base = date(2026, 11, 10)
    for i in range(n_sessions):
        d = base - timedelta(days=n_sessions - 1 - i)
        mid = 100.0 + i
        session.add(MarketPrice(
            asset_id=asset_id,
            provider=provider,
            trade_date=d,
            open=mid - 0.5,
            high=mid + 1.0,
            low=mid - 1.0,
            close=mid,
            volume=1000 + i,
        ))
    session.commit()


def test_levels_are_window_extremes(sqlite_session):
    a = Asset(exchange="HKEX", ticker="0700", name="Tencent")
    sqlite_session.add(a)
    sqlite_session.flush()
    # 25 bars; with window 20 only the most recent 20 count.
    _seed(sqlite_session, a.id, 25)

    levels = support_resistance(sqlite_session, a.id, window_sessions=20)
    d = levels_to_dict(levels)

    # Bars are 100.0 + i over 25 days: i in 0..24. Last 20 bars -> i in 5..24.
    # low  = 99.0 + i  -> min over i=5..24 = 104.0
    # high = 101.0 + i -> max over i=5..24 = 125.0
    assert d["support"] == 104.0
    assert d["resistance"] == 125.0
    assert d["data_sufficient"] is True
    assert d["available_sessions"] == 20
    assert d["window_sessions"] == 20
    assert "min(low)" in d["method"] and "max(high)" in d["method"]
    assert d["as_of"] == "2026-11-10"


def test_full_window_when_fewer_bars_exist(sqlite_session):
    a = Asset(exchange="KRX", ticker="005930", name="Samsung Electronics")
    sqlite_session.add(a)
    sqlite_session.flush()
    _seed(sqlite_session, a.id, 5)

    levels = support_resistance(sqlite_session, a.id, window_sessions=20)
    d = levels_to_dict(levels)
    # 5 bars: i in 0..4 -> low min = 99.0, high max = 105.0
    assert d["support"] == 99.0
    assert d["resistance"] == 105.0
    assert d["data_sufficient"] is True
    assert d["available_sessions"] == 5


def test_insufficient_history_is_never_fabricated(sqlite_session):
    a = Asset(exchange="KRX", ticker="035420", name="NAVER")
    sqlite_session.add(a)
    sqlite_session.flush()
    _seed(sqlite_session, a.id, 1)  # one bar -> fewer than the 2 usable minimum

    levels = support_resistance(sqlite_session, a.id, window_sessions=20)
    d = levels_to_dict(levels)
    assert d["support"] is None
    assert d["resistance"] is None
    assert d["data_sufficient"] is False
    assert d["available_sessions"] == 1


def test_no_bars_at_all(sqlite_session):
    a = Asset(exchange="KRX", ticker="035720", name="Kakao")
    sqlite_session.add(a)
    sqlite_session.flush()

    levels = support_resistance(sqlite_session, a.id, window_sessions=20)
    d = levels_to_dict(levels)
    assert d["support"] is None
    assert d["resistance"] is None
    assert d["data_sufficient"] is False
    assert d["as_of"] is None
    assert "no usable stored bars" in d["basis"]
