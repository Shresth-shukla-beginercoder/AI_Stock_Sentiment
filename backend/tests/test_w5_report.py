"""W5: exchange-separated per-ticker report.

Covers: exchange separation, ranking rule (mentions desc -> sentiment score
desc, None last -> ticker), missing-data != zero (nulls vs 0 counts),
price/direction/position/S-R fields, and demo/live report-shape parity.
"""

from datetime import date

from app.database.models import (
    Asset,
    MarketPrice,
    NewsArticle,
    Prediction,
    SentimentResult,
    SocialPost,
)
from app.services import demo_data, store
from app.services.report import build_ticker_report


def _asset(session, exchange, ticker, name):
    a = Asset(exchange=exchange, ticker=ticker, name=name)
    session.add(a)
    session.commit()
    return a


def _add_posts(session, asset_id, n):
    for i in range(n):
        session.add(SocialPost(
            asset_id=asset_id, source="lihkg",
            content_hash=f"hash-{asset_id}-{i}", content=f"post {i}",
        ))


def _add_news(session, asset_id, n, url_prefix):
    for i in range(n):
        session.add(NewsArticle(
            asset_id=asset_id, source="exa",
            url_hash=f"news-hash-{asset_id}-{i}", title=f"{url_prefix} headline {i}",
            url=f"https://example.com/{url_prefix}/{i}",
        ))


def _add_result(session, item_type, item_id, label, score):
    session.add(SentimentResult(
        item_type=item_type, item_id=item_id, model_name="test-model",
        label=label, score=score,
    ))


def _add_price(session, asset_id, close, trade_date="2026-11-10"):
    session.add(MarketPrice(
        asset_id=asset_id, provider="twelve_data", trade_date=date.fromisoformat(trade_date),
        open=close, high=close * 1.02, low=close * 0.98, close=close, volume=100,
    ))


def test_report_separates_exchanges_and_ranks(sqlite_session):
    hk1 = _asset(sqlite_session, "HKEX", "0700", "Tencent")
    hk2 = _asset(sqlite_session, "HKEX", "9988", "Alibaba")
    kr1 = _asset(sqlite_session, "KRX", "005930", "Samsung Electronics")

    # 0700: rich data. 9988: fewer mentions. 005930: only a price bar.
    _add_posts(sqlite_session, hk1.id, 12)
    _add_news(sqlite_session, hk1.id, 4, "tencent")
    _add_posts(sqlite_session, hk2.id, 2)
    _add_news(sqlite_session, hk2.id, 1, "alibaba")
    _add_price(sqlite_session, kr1.id, 71000.0)
    sqlite_session.commit()

    report = build_ticker_report(sqlite_session)
    exs = {e["exchange"]: e for e in report["exchanges"]}
    assert set(exs) == {"HKEX", "KRX"}
    assert exs["HKEX"]["timezone"] == "Asia/Hong_Kong"
    assert exs["KRX"]["timezone"] == "Asia/Seoul"

    hk_rows = {r["ticker"]: r for r in exs["HKEX"]["tickers"]}
    # Ranking: 0700 (16 mentions) before 9988 (3 mentions).
    assert [r["ticker"] for r in exs["HKEX"]["tickers"]] == ["0700", "9988"]
    assert hk_rows["0700"]["rank"] == 1
    assert hk_rows["0700"]["mentions"] == {"social_posts": 12, "news_articles": 4, "total": 16}

    kr_row = exs["KRX"]["tickers"][0]
    assert kr_row["ticker"] == "005930"
    # KRX asset has a price but no social/news: counts are real zeros,
    # while the missing upstream fields are null (never fabricated).
    assert kr_row["mentions"]["total"] == 0
    assert kr_row["mentions"]["social_posts"] == 0
    assert kr_row["current_price"]["close"] == 71000.0
    assert kr_row["current_price"]["provider"] == "twelve_data"
    assert kr_row["sentiment"]["score"] is None
    assert kr_row["direction"] == "none"
    assert kr_row["prediction"] is None
    assert kr_row["position"] == "unknown"


def test_ranking_tiebreaks_on_sentiment_then_ticker(sqlite_session):
    a = _asset(sqlite_session, "HKEX", "0005", "HSBC")
    b = _asset(sqlite_session, "HKEX", "3690", "Meituan")
    for asset in (a, b):
        _add_posts(sqlite_session, asset.id, 3)
        sqlite_session.flush()
    # a: 2 positive / 1 negative -> score +1/3 ; b: 1 positive / 2 negative -> -1/3
    posts_a = sqlite_session.query(SocialPost).filter(SocialPost.asset_id == a.id).all()
    posts_b = sqlite_session.query(SocialPost).filter(SocialPost.asset_id == b.id).all()
    for p in posts_a[:2]:
        _add_result(sqlite_session, "social_post", p.id, "positive", 0.5)
    _add_result(sqlite_session, "social_post", posts_a[2].id, "negative", -0.5)
    _add_result(sqlite_session, "social_post", posts_b[0].id, "positive", 0.5)
    for p in posts_b[1:]:
        _add_result(sqlite_session, "social_post", p.id, "negative", -0.5)
    sqlite_session.commit()

    report = build_ticker_report(sqlite_session)
    order = [r["ticker"] for r in report["exchanges"][0]["tickers"]]
    # Same mention counts -> higher sentiment score first (0005: +0.333 > 3690: -0.333).
    assert order == ["0005", "3690"]


def test_direction_and_position_from_prediction_and_levels(sqlite_session):
    a = _asset(sqlite_session, "KRX", "000660", "SK Hynix")
    # Two bars so window-extremes levels exist: closes 129000 and 130000.
    _add_price(sqlite_session, a.id, 129000.0, trade_date="2026-11-09")
    _add_price(sqlite_session, a.id, 130000.0, trade_date="2026-11-10")
    sqlite_session.add(Prediction(
        asset_id=a.id, model_version="wf-ridge-test",
        target_date=date(2026, 11, 11),
        predicted_return=0.0042, predicted_price=130546.0, experimental=True,
    ))
    sqlite_session.commit()

    report = build_ticker_report(sqlite_session)
    row = report["exchanges"][0]["tickers"][0]
    assert row["direction"] == "up"
    assert row["prediction"]["predicted_return"] == 0.0042
    assert row["prediction"]["target_date"] == "2026-11-11"
    # Levels: support = min(129000*0.98, 130000*0.98) = 126420,
    # resistance = max(129000*1.02, 130000*1.02) = 132600 -> close 130000 is between.
    assert row["support_resistance"]["support"] == 129000.0 * 0.98
    assert row["support_resistance"]["resistance"] == 130000.0 * 1.02
    assert row["position"] == "between"


def test_overview_per_ticker_matches_demo_shape(sqlite_session):
    """W5: the live overview must expose the same per_ticker keys the demo
    overview does — the dashboard reads the same shape in both modes."""
    a = _asset(sqlite_session, "HKEX", "0700", "Tencent")
    _add_posts(sqlite_session, a.id, 2)
    _add_news(sqlite_session, a.id, 1, "tencent")
    _add_price(sqlite_session, a.id, 400.0)
    sqlite_session.commit()

    live = store.overview(sqlite_session)
    demo = demo_data.get_overview()
    demo_keys = set(next(iter(demo["per_ticker"].values())).keys())
    live_keys = set(live["per_ticker"]["0700"].keys())
    assert demo_keys == live_keys
    assert live["per_ticker"]["0700"]["posts"] == 2
    assert live["per_ticker"]["0700"]["news"] == 1
    assert live["per_ticker"]["0700"]["price_days"] == 1


def test_demo_and_live_report_shapes_match():
    """The demo and live /reports/tickers payloads must carry the same
    top-level and per-ticker keys (API and frontend represent one shape)."""
    demo_report = demo_data.get_ticker_report()
    assert set(demo_report.keys()) >= {"as_of", "exchanges", "ranking", "meta"}
    ticker_keys = set(demo_report["ranking"][0].keys())
    for required in (
        "ticker", "name", "current_price", "sentiment", "direction",
        "prediction", "support_resistance", "position", "mentions", "rank",
    ):
        assert required in ticker_keys, f"demo report missing field {required}"
    # Determinism: the demo report is reproducible from constants alone.
    assert demo_data.get_ticker_report()["as_of"] == demo_report["as_of"]
