"""Regression tests: asset lookup by raw ticker OR vendor provider_ticker.

Context (Option 1 fix, 2026-11-10): ``store._match_asset`` previously used
``COALESCE(provider_ticker, ticker)`` — when a row carried a vendor symbol
(``provider_ticker='1810.HK'``) the raw ticker ('1810') stopped resolving, so
``GET /api/assets/1810`` returned 404 even though ``GET /api/assets`` listed
the same asset. The matcher now accepts either identifier.

All store-level tests use the project's in-memory SQLite fixture pattern
(test-only scaffolding; the app itself never calls ``create_all``).
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database import models  # noqa: F401  (register all tables)
from app.database.models import Asset, MarketPrice, SocialPost
from app.services import store


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)  # test fixture only
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    yield s
    s.close()
    engine.dispose()


@pytest.fixture()
def xiaomi(session) -> Asset:
    """The production-shaped row: raw ticker + vendor provider_ticker."""
    a = Asset(
        exchange="HKEX",
        ticker="1810",
        name="Xiaomi",
        provider_ticker="1810.HK",
        confirmed=False,
        active=True,
    )
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


# --- store-level matching ----------------------------------------------------

def test_lookup_by_raw_ticker(session, xiaomi):
    """GET /api/assets/1810 must resolve the asset (the reported bug)."""
    found = store.asset_or_none(session, "1810")
    assert found is not None
    assert found.id == xiaomi.id
    assert found.provider_ticker == "1810.HK"


def test_lookup_by_provider_ticker(session, xiaomi):
    """GET /api/assets/1810.HK must resolve the *same* asset."""
    found = store.asset_or_none(session, "1810.HK")
    assert found is not None
    assert found.id == xiaomi.id


def test_lookup_unknown_ticker_is_none(session, xiaomi):
    """Unknown identifiers stay 404-capable (store returns None)."""
    assert store.asset_or_none(session, "9999") is None
    assert store.asset_or_none(session, "9999.HK") is None
    assert store.asset_or_none(session, "0005") is None  # no such row seeded


def test_lookup_null_provider_ticker_still_resolves(session):
    """A row with no vendor symbol resolves by its raw ticker only."""
    a = Asset(exchange="KRX", ticker="005380", name="Hyundai Motor", provider_ticker=None)
    session.add(a)
    session.commit()
    assert store.asset_or_none(session, "005380").id == a.id
    assert store.asset_or_none(session, "005380.KS") is None  # not a known id


def test_list_assets_unaffected_by_lookup_change(session, xiaomi):
    """The list endpoint keeps returning every row, raw ticker surfaced."""
    rows = store.list_assets(session)
    assert [r["ticker"] for r in rows] == ["1810"]
    assert rows[0]["confirmed"] is False  # unconfirmed rows are listed as before


# --- subresources share _match_asset ------------------------------------------

def test_list_prices_resolves_via_both_identifiers(session, xiaomi):
    session.add(
        MarketPrice(
            asset_id=xiaomi.id,
            provider="twelvedata",
            trade_date=date(2026, 11, 9),
            close=50.0,
        )
    )
    session.commit()
    for key in ("1810", "1810.HK"):
        rows, total = store.list_prices(session, key, 50, 0)
        assert total == 1
        assert rows[0]["close"] == 50.0
    # unknown ticker -> honest empty, not an error
    rows, total = store.list_prices(session, "0005", 50, 0)
    assert total == 0 and rows == []


def test_list_posts_resolves_via_raw_ticker(session, xiaomi):
    session.add(
        SocialPost(asset_id=xiaomi.id, source="lihkg", content_hash="h-1810", content="post")
    )
    session.commit()
    rows, total = store.list_posts(session, "1810", 50, 0)
    assert total == 1 and rows[0]["source"] == "lihkg"
    rows, total = store.list_posts(session, "1810.HK", 50, 0)
    assert total == 1


def test_sentiment_no_data_resolves_via_provider_ticker(session, xiaomi):
    out = store.sentiment_for_ticker(session, "1810.HK")
    assert out["state"] == "no_data"
    assert out["asset_ticker"] == "1810.HK"


# --- route-level (the exact reported requests) --------------------------------

def test_route_get_asset_200_200_404(monkeypatch, tmp_path):
    """GET /api/assets/1810 and /api/assets/1810.HK -> 200; unknown -> 404."""
    from fastapi.testclient import TestClient

    from app.main import app
    from app.database.session import get_session
    import app.api.routes as routes
    from app.core.config import Settings

    # File-based SQLite: TestClient runs requests on a different thread than
    # this test, and an in-memory DB would be empty (or thread-confined) there.
    engine = create_engine(f"sqlite:///{tmp_path}/lookup.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    a = Asset(
        exchange="HKEX", ticker="1810", name="Xiaomi",
        provider_ticker="1810.HK", confirmed=False,
    )
    s = factory()
    s.add(a)
    s.commit()
    s.close()

    def _override_get_session():
        yield factory()

    live_settings = Settings(data_mode="live")
    monkeypatch.setattr(routes, "get_settings", lambda: live_settings)
    app.dependency_overrides[get_session] = _override_get_session
    try:
        client = TestClient(app)

        r = client.get("/api/assets/1810")
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["ticker"] == "1810"
        assert body["data"]["provider_ticker"] == "1810.HK"
        assert body["data_mode"] == "live"

        r2 = client.get("/api/assets/1810.HK")
        assert r2.status_code == 200
        assert r2.json()["data"]["ticker"] == "1810"  # same row, other identifier

        r3 = client.get("/api/assets/0005.HK")
        assert r3.status_code == 404
        assert r3.json()["error"]["code"] == "not_found"
        assert "0005.HK" in r3.json()["error"]["message"]
    finally:
        app.dependency_overrides.pop(get_session, None)
        monkeypatch.undo()
        engine.dispose()
