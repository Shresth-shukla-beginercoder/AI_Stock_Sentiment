"""Phase 5 collector tests.

Three layers:
1. Normalisation (pure, hermetic) — symbol/URL/text/timestamp/hash + OHLCV.
2. Provider clients with mocked transports/SDKs — parsing, error classification,
   bounded retry, dedupe, missing-value -> NULL. No network.
3. Persistence against real Postgres (skipped automatically when the DB is
   unreachable) — idempotent upserts, unique constraints, NULL preservation,
   transaction rollback.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest

from app.collectors.normalize import (
    normalize_symbol,
    url_hash,
    canonical_url,
    clean_text,
    engagement_int,
    parse_timestamp,
    social_content_hash,
    ohlv_to_price_row,
)
from app.collectors.provider import PriceRow
from app.collectors.exceptions import (
    AuthError,
    RateLimitError,
    InvalidResponseError,
    SymbolNotFoundError,
)
from app.collectors.twelve_data import TwelveDataProvider
from app.collectors.exa import ExaNewsCollector
from app.collectors.apify import ApifySocialCollector


def _settings(**over):
    from app.core.config import Settings

    base = dict(
        provider_timeout_seconds=5.0,
        provider_max_retries=0,
        provider_retry_base_delay_seconds=0.0,
        provider_retry_backoff_factor=1.0,
        provider_retry_max_delay_seconds=0.0,
        provider_batch_limit=5,
        collection_window_days=10,
        data_mode="demo",
    )
    base.update(over)
    return Settings(**base)


# =====================================================================
# 1. Normalisation
# =====================================================================
def test_normalize_symbol_hkex():
    assert normalize_symbol("0700", "HKEX") == "0700.HK"
    assert normalize_symbol("700", "HKEX") == "0700.HK"
    assert normalize_symbol("0005", "HKEX") == "0005.HK"


def test_normalize_symbol_krx():
    assert normalize_symbol("005930", "KRX") == "005930.KS"
    assert normalize_symbol("5930", "KRX") == "005930.KS"


def test_normalize_symbol_already_suffixed():
    assert normalize_symbol("0700.HK", "HKEX") == "0700.HK"
    assert normalize_symbol("005930.KS", "KRX") == "005930.KS"


def test_normalize_symbol_no_exchange():
    assert normalize_symbol("abc", None) == "ABC"


def test_url_hash_deterministic_and_canonical():
    # fragment + trailing slash + query order + host case must all collapse;
    # path case is significant (RFC), so keep it identical here.
    a = url_hash("https://Example.com/Article/?b=2&a=1#frag")
    b = url_hash("https://example.com/Article?a=1&b=2")
    assert a == b
    # a different path hashes differently
    assert url_hash("https://example.com/other") != a
    assert url_hash(None) is None
    assert url_hash("   ") is None


def test_clean_text_nfkc_and_html():
    assert clean_text("  hello&nbsp;world<br>foo ") == "hello world foo"
    # entities are decoded, then the resulting HTML tags are stripped
    assert clean_text("&lt;code&gt;x&lt;/code&gt;") == "x"
    assert clean_text(None) is None
    assert clean_text("   ") == ""


def test_engagement_int():
    assert engagement_int(None) is None
    assert engagement_int("42") == 42
    assert engagement_int(3.0) == 3
    assert engagement_int(True) is None        # bool is not a count
    assert engagement_int(-1) is None           # negative -> unknown
    assert engagement_int("abc") is None


def test_parse_timestamp_variants():
    aware = parse_timestamp("2026-01-05T09:00:00+09:00")
    assert aware == datetime(2026, 1, 5, 0, 0, tzinfo=timezone.utc)
    naive = parse_timestamp("2026-01-05T09:00:00")  # no tz -> coerced to UTC
    assert naive == datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)
    assert parse_timestamp(None) is None
    assert parse_timestamp("not-a-date") is None
    epoch = parse_timestamp(1700000000)
    assert epoch.tzinfo == timezone.utc


def test_social_content_hash_deterministic():
    a = social_content_hash("telegram", "hi there", "123")
    b = social_content_hash("telegram", "hi there", "123")
    c = social_content_hash("lihkg", "hi there", "123")
    assert a == b
    assert a != c


def test_ohlv_to_price_row_nulls_preserved():
    row = ohlv_to_price_row("0700", "2026-01-05", None, None, None, "380.5", None)
    assert row.close == 380.5
    assert row.open is None
    assert row.high is None
    assert row.low is None
    assert row.volume is None
    assert row.trade_date.tzinfo is not None  # aware UTC
    assert row.trade_date.date() == date(2026, 1, 5)


def test_ohlv_missing_close_is_error():
    with pytest.raises(InvalidResponseError):
        ohlv_to_price_row("0700", "2026-01-05", "1", "2", "0.5", None)


def test_ohlv_impossible_bar_rejected():
    with pytest.raises(InvalidResponseError):
        ohlv_to_price_row("0700", "2026-01-05", "10", "5", "1", "8")  # high < close


def test_ohlv_malformed_volume_becomes_null():
    # Sane OHLC (high>=close>=low) but a non-numeric volume -> NULL, not 0.
    row = ohlv_to_price_row("0700", "2026-01-05", "1", "3", "0.5", "2", "oops")
    assert row.volume is None


def test_pricerow_rejects_naive_datetime():
    with pytest.raises(ValueError):
        PriceRow("0700", datetime(2026, 1, 5, 16, 0), None, None, None, 1.0)


# =====================================================================
# 2. Twelve Data (mocked transport)
# =====================================================================
def _td_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_twelve_data_valid_parse():
    def handler(req: httpx.Request) -> httpx.Response:
        assert b"apikey=" in req.url.query  # key travels in the query string
        return httpx.Response(200, json={
            "status": "ok",
            "meta": {"exchange_timezone": "Asia/Hong_Kong"},
            "values": [
                {"datetime": "2026-01-05", "open": "1", "high": "3", "low": "0.5",
                 "close": "2.5", "volume": "100"},
                {"datetime": "2026-01-06", "open": "", "high": "4", "low": "1",
                 "close": "3.5"},  # missing open -> None; missing volume -> None
            ],
        })

    p = TwelveDataProvider("0700", date(2026, 1, 1), date(2026, 1, 31),
                          exchange="HKEX", settings=_settings(), api_key="k",
                          client=_td_client(handler))
    rows = p.get_daily_prices()
    assert len(rows) == 2
    assert rows[0].close == 2.5 and rows[0].volume == 100
    assert rows[1].open is None and rows[1].volume is None
    assert rows[0].trade_date < rows[1].trade_date  # ascending


def test_twelve_data_auth_failure():
    def handler(req):
        return httpx.Response(401, json={"status": "error", "code": 401, "message": "bad key"})
    p = TwelveDataProvider("AAPL", date(2026, 1, 1), date(2026, 1, 31),
                          settings=_settings(), api_key="k", client=_td_client(handler))
    with pytest.raises(AuthError):
        p.get_daily_prices()


def test_twelve_data_plan_gated_404():
    def handler(req):
        return httpx.Response(404, json={"status": "error", "code": 404,
                                         "message": "available starting with the Grow plan"})
    p = TwelveDataProvider("0700", date(2026, 1, 1), date(2026, 1, 31),
                          exchange="HKEX", settings=_settings(), api_key="k",
                          client=_td_client(handler))
    with pytest.raises(SymbolNotFoundError):
        p.get_daily_prices()


def test_tweline_data_no_data_empty_values():
    def handler(req):
        return httpx.Response(200, json={"status": "ok", "values": []})
    p = TwelveDataProvider("AAPL", date(2026, 1, 1), date(2026, 1, 31),
                          settings=_settings(), api_key="k", client=_td_client(handler))
    assert p.get_daily_prices() == []


def test_twelve_data_invalid_response():
    def handler(req):
        return httpx.Response(200, json={"status": "ok", "values": "not-a-list"})
    p = TwelveDataProvider("AAPL", date(2026, 1, 1), date(2026, 1, 31),
                          settings=_settings(), api_key="k", client=_td_client(handler))
    with pytest.raises(InvalidResponseError):
        p.get_daily_prices()


def test_twelve_data_rate_limit_and_retry():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"status": "error", "code": 429,
                                            "message": "rate limited"})
        return httpx.Response(200, json={"status": "ok", "values": []})

    # max_retries=1, zero wait -> first 429 is retried, second succeeds.
    p = TwelveDataProvider("AAPL", date(2026, 1, 1), date(2026, 1, 31),
                          settings=_settings(provider_max_retries=1), api_key="k",
                          client=_td_client(handler))
    assert p.get_daily_prices() == []
    assert calls["n"] == 2


def test_twelve_data_rate_limit_exhausts():
    def handler(req):
        return httpx.Response(429, json={"status": "error", "code": 429})

    p = TwelveDataProvider("AAPL", date(2026, 1, 1), date(2026, 1, 31),
                          settings=_settings(provider_max_retries=0), api_key="k",
                          client=_td_client(handler))
    with pytest.raises(RateLimitError):
        p.get_daily_prices()


def test_twelve_data_missing_key():
    p = TwelveDataProvider("AAPL", date(2026, 1, 1), date(2026, 1, 31),
                          settings=_settings(twelve_data_api_key=None), api_key="",
                          client=_td_client(lambda r: httpx.Response(200, json={})))
    with pytest.raises(AuthError):
        p.get_daily_prices()


# =====================================================================
# 3. Exa (mocked SDK)
# =====================================================================
def _fake_exa(results, *, fail=None):
    class _Exa:
        def search(self, query, *a, **k):
            if fail is not None:
                raise fail
            return SimpleNamespace(results=results)
    return _Exa()


def _fake_result(url, title="T", pub="2026-01-05T00:00:00Z", author="a", text="<b>x</b>", rid="r1"):
    return SimpleNamespace(url=url, id=rid, title=title, published_date=pub,
                           author=author, text=text)


def test_exa_maps_and_dedupes():
    exa = _fake_exa([
        _fake_result("https://news.co/a?x=1#f"),
        _fake_result("https://news.co/a?x=1"),   # same canonical URL -> dedupe
        _fake_result("https://news.co/b", text=None, pub=None),  # no text/date
    ])
    coll = ExaNewsCollector(settings=_settings(), exa=exa)
    items = coll.search("tencent news")
    # two unique URLs survive; the duplicate is dropped
    assert len(items) == 2
    urls = {i.url_hash for i in items}
    assert len(urls) == 2
    # missing published_date stays None, not a fake date
    b = [i for i in items if "news.co/b" in canonical_url(i.url)][0]
    assert b.published_at is None
    assert b.body is None


def test_exa_missing_date_handled_honestly():
    exa = _fake_exa([_fake_result("https://x.co/1", pub=None)])
    coll = ExaNewsCollector(settings=_settings(), exa=exa)
    items = coll.search("q")
    assert items[0].published_at is None


def test_exa_empty_query_rejected():
    coll = ExaNewsCollector(settings=_settings(), exa=_fake_exa([]))
    with pytest.raises(InvalidResponseError):
        coll.search("   ")


def test_exa_rate_limit_wrapped():
    exa = _fake_exa([], fail=Exception("429 Too Many Requests"))
    coll = ExaNewsCollector(settings=_settings(), exa=exa)
    with pytest.raises(RateLimitError):
        coll.search("q")


def test_exa_auth_wrapped():
    exa = _fake_exa([], fail=Exception("403 unauthorized: invalid api key"))
    coll = ExaNewsCollector(settings=_settings(), exa=exa)
    with pytest.raises(AuthError):
        coll.search("q")


# =====================================================================
# 4. Apify (mocked client)
# =====================================================================
def _fake_apify(actor_get_result=None, *, get_exc=None, validate=True, items=()):
    def _get():
        if get_exc is not None:
            raise get_exc
        return actor_get_result

    class _Run:
        default_dataset_id = "ds1"

    class _Dataset:
        def list_items(self, limit=None, offset=0):
            return SimpleNamespace(items=list(items))

    class _Client:
        def actor(self, ref):
            return SimpleNamespace(
                get=_get,
                validate_input=lambda inp: validate,
                call=lambda **k: _Run(),
            )

        def dataset(self, ds_id):
            return _Dataset()

        def actors(self):
            raise NotImplementedError

    return _Client()


def _fake_actor_info(versions_input_schema=None):
    return SimpleNamespace(
        id="actor-abc", is_public=True, is_deprecated=False,
        versions=[SimpleNamespace(input_schema=versions_input_schema or {"type": "object"})],
        example_run_input={"keyword": "x"},
    )


def test_apify_verify_actor_available():
    cli = _fake_apify(actor_get_result=_fake_actor_info())
    coll = ApifySocialCollector(settings=_settings(), client=cli)
    avail = coll.verify_actor("ns/name", platform="telegram")
    assert avail.available is True
    assert avail.actor_id == "actor-abc"
    assert avail.is_public is True
    assert avail.input_schema is not None


def test_apify_verify_actor_not_found():
    cli = _fake_apify(get_exc=Exception("HTTP 404 not found"))
    coll = ApifySocialCollector(settings=_settings(), client=cli)
    avail = coll.verify_actor("ns/missing")
    assert avail.available is False
    assert "not found" in avail.reason.lower() or "not accessible" in avail.reason.lower()


def test_apify_verify_actor_access_denied():
    cli = _fake_apify(get_exc=Exception("HTTP 403 forbidden"))
    coll = ApifySocialCollector(settings=_settings(), client=cli)
    avail = coll.verify_actor("ns/private")
    assert avail.available is False
    assert "access denied" in avail.reason.lower()


def test_apify_maps_social_items():
    cli = _fake_apify(items=[
        {"item": {"id": "p1", "text": "  <b>great news</b>  ", "date": "2026-01-05",
                  "likes": 12}},
        {"item": {"message": "another post", "createdAt": "2026-01-06"}},
        {"item": {"no_text_field": True}},  # no usable text -> skipped
    ])
    coll = ApifySocialCollector(settings=_settings(), client=cli)
    items = coll.to_social_items(list(coll.fetch_items(SimpleNamespace(default_dataset_id="ds1"))),
                                 platform="telegram")
    assert len(items) == 2
    assert items[0].content == "great news"
    assert items[0].engagement == 12
    assert items[0].external_id == "p1"
    assert items[1].engagement is None
    assert items[0].content_hash == social_content_hash("telegram", "great news", "p1")


def test_apify_run_rejects_invalid_schema():
    cli = _fake_apify(validate=False, actor_get_result=_fake_actor_info())
    coll = ApifySocialCollector(settings=_settings(), client=cli)
    from app.collectors.exceptions import InvalidResponseError
    with pytest.raises(InvalidResponseError):
        coll.run_actor("ns/name", {"foo": "bar"})


# =====================================================================
# 5. Persistence (real Postgres; skipped when unreachable)
# =====================================================================
def _db_available():
    try:
        from app.database.session import get_session_factory
        factory = get_session_factory()
        with factory() as s:
            s.execute(__import__("sqlalchemy").text("SELECT 1"))
        return True
    except Exception:
        return False


needs_db = pytest.mark.skipif(not _db_available(), reason="Postgres unreachable")

_EXCH = "PHASE5X"


def _wipe_exchange(ticker: str) -> None:
    """Idempotent cleanup of PHASE5X test rows (safe after a crashed run).

    Deletes children first (news uses SET NULL, so it must be removed
    explicitly), then the asset. A fresh committed transaction each time.
    """
    from app.database.session import get_session_factory
    from app.database.models import Asset, MarketPrice, NewsArticle, SocialPost
    from sqlalchemy import delete, select

    factory = get_session_factory()
    with factory() as s:
        s.rollback()  # discard any pending/aborted state
        ids = select(Asset.id).where(Asset.exchange == _EXCH, Asset.ticker == ticker)
        s.execute(delete(MarketPrice).where(MarketPrice.asset_id.in_(ids)))
        s.execute(delete(SocialPost).where(SocialPost.asset_id.in_(ids)))
        s.execute(delete(NewsArticle).where(NewsArticle.asset_id.in_(ids)))
        s.execute(delete(Asset).where(Asset.exchange == _EXCH, Asset.ticker == ticker))
        s.commit()


@needs_db
def test_persist_market_idempotent_and_nulls():
    from app.database.session import get_session_factory
    from app.database.models import Asset, MarketPrice
    from app.services.persist import persist_market_prices
    from sqlalchemy import select

    _wipe_exchange("P5T")
    factory = get_session_factory()
    with factory() as s:
        a = Asset(exchange=_EXCH, ticker="P5T", name="P5 test", confirmed=True)
        s.add(a); s.commit(); s.refresh(a)
        asset_id = a.id
        try:
            rows = [
                PriceRow("P5T", datetime(2026, 1, 5, tzinfo=timezone.utc),
                         None, None, None, 10.0, None),
                PriceRow("P5T", datetime(2026, 1, 6, tzinfo=timezone.utc),
                         9.0, 11.0, 8.0, 10.5, 1000),
            ]
            r1 = persist_market_prices(s, asset_id, "twelvedata", rows)
            s.commit()
            assert r1.inserted == 2 and r1.skipped_duplicates == 0

            r2 = persist_market_prices(s, asset_id, "twelvedata", rows)
            s.commit()
            assert r2.inserted == 0 and r2.skipped_duplicates == 2

            total = s.execute(select(MarketPrice).where(
                MarketPrice.asset_id == asset_id,
                MarketPrice.provider == "twelvedata"
            )).scalars().all()
            assert len(total) == 2

            first = [m for m in total if m.trade_date == date(2026, 1, 5)][0]
            assert first.open is None and first.close == 10.0 and first.volume is None
        finally:
            s.rollback()
            _wipe_exchange("P5T")


@needs_db
def test_persist_news_dedupe_by_url_hash():
    from app.database.session import get_session_factory
    from app.database.models import Asset, NewsArticle
    from app.services.persist import persist_news
    from app.collectors.exa import NewsItem
    from app.collectors.normalize import url_hash, parse_timestamp
    from sqlalchemy import select

    _wipe_exchange("P5N")
    factory = get_session_factory()
    with factory() as s:
        a = Asset(exchange=_EXCH, ticker="P5N", name="P5 news", confirmed=True)
        s.add(a); s.commit(); s.refresh(a)
        asset_id = a.id
        try:
            uh = url_hash("https://news.example.org/one")
            item = NewsItem(url="https://news.example.org/one", url_hash=uh,
                            title="Headline", body="Body",
                            published_at=parse_timestamp("2026-01-01T00:00:00Z"),
                            author="a", source="news.example.org")
            r1 = persist_news(s, asset_id, [item]); s.commit()
            assert r1.inserted == 1
            r2 = persist_news(s, asset_id, [item]); s.commit()
            assert r2.inserted == 0 and r2.skipped_duplicates == 1
            got = s.execute(select(NewsArticle).where(NewsArticle.url_hash == uh)).scalars().all()
            assert len(got) == 1
        finally:
            s.rollback()
            _wipe_exchange("P5N")


@needs_db
def test_persist_social_dedupe_and_rollback():
    from app.database.session import get_session_factory
    from app.database.models import Asset, SocialPost
    from app.services.persist import persist_social
    from app.collectors.apify import SocialPostItem
    from app.collectors.normalize import social_content_hash, parse_timestamp
    from sqlalchemy import select

    _wipe_exchange("P5S")
    factory = get_session_factory()
    with factory() as s:
        a = Asset(exchange=_EXCH, ticker="P5S", name="P5 social", confirmed=True)
        s.add(a); s.commit(); s.refresh(a)
        asset_id = a.id
        try:
            ch = social_content_hash("telegram", "hello", "42")
            item = SocialPostItem(source="telegram", content_hash=ch, content="hello",
                                  url=None, published_at=parse_timestamp("2026-01-01T00:00:00Z"),
                                  engagement=5, external_id="42")
            r1 = persist_social(s, asset_id, [item]); s.commit()
            assert r1.inserted == 1
            r2 = persist_social(s, asset_id, [item]); s.commit()
            assert r2.inserted == 0 and r2.skipped_duplicates == 1
            assert len(s.execute(select(SocialPost).where(
                SocialPost.asset_id == asset_id)).scalars().all()) == 1

            # a rolled-back insert leaves no trace
            ch2 = social_content_hash("telegram", "bye", "43")
            s.add(SocialPost(asset_id=asset_id, source="telegram", content_hash=ch2,
                             content="bye",
                             published_at=parse_timestamp("2026-01-01T00:00:00Z")))
            s.rollback()
            assert len(s.execute(select(SocialPost).where(
                SocialPost.asset_id == asset_id, SocialPost.content_hash == ch2)).scalars().all()) == 0
        finally:
            s.rollback()
            _wipe_exchange("P5S")
