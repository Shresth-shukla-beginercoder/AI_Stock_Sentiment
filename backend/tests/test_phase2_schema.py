"""Phase 2 schema tests.

Test fixtures use in-memory SQLite with ``Base.metadata.create_all`` — this is
test-only scaffolding; the application never calls create_all (CLAUDE.md).
PostgreSQL-specific behaviour (JSONB, timestamptz storage) is verified in the
Docker gate instead.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import sessionmaker

from app.database.base import Base
from app.database import models  # noqa: F401  (register all tables)
from app.database.models import (
    Asset,
    CollectionJob,
    MarketPrice,
    ModelEvaluation,
    NewsArticle,
    Prediction,
    SentimentResult,
    SocialPost,
)

UTC = timezone.utc


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)  # test fixture only
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    s = Session()
    yield s
    s.close()
    engine.dispose()


def _asset(session, ticker="0700", exchange="HKEX") -> Asset:
    a = Asset(exchange=exchange, ticker=ticker, name="Tencent", provider_ticker="0700.HK")
    session.add(a)
    session.commit()
    session.refresh(a)
    return a


# --- table inventory --------------------------------------------------------
def test_all_eight_tables_exist(session):
    names = {t.name for t in Base.metadata.sorted_tables}
    expected = {
        "assets",
        "social_posts",
        "news_articles",
        "market_prices",
        "sentiment_results",
        "predictions",
        "model_evaluations",
        "collection_jobs",
    }
    assert expected <= names, f"missing tables: {expected - names}"
    # SQLite fixture already built them; confirm session can query each
    for model in (
        Asset,
        SocialPost,
        NewsArticle,
        MarketPrice,
        SentimentResult,
        Prediction,
        ModelEvaluation,
        CollectionJob,
    ):
        assert session.execute(select(model.id).limit(1)) is not None


# --- unique constraints (dedupe) -------------------------------------------
def test_duplicate_asset_rejected(session):
    a = _asset(session)
    session.add(Asset(exchange="HKEX", ticker="0700", name="Tencent dup"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_duplicate_social_post_rejected(session):
    a = _asset(session)
    base = datetime.now(UTC)
    # two distinct posts, different hashes — both fine
    for i, h in enumerate(["ab" * 32, "cd" * 32]):
        session.add(
            SocialPost(
                asset_id=a.id,
                source="x",
                content_hash=h,
                content=f"post {i}",
                published_at=base + timedelta(hours=i),
            )
        )
        session.commit()
    # identical (source, content_hash) must be rejected
    session.add(
        SocialPost(
            asset_id=a.id,
            source="x",
            content_hash="ab" * 32,
            content="re-inserted",
            published_at=base + timedelta(hours=5),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_duplicate_news_article_rejected(session):
    a = _asset(session)
    session.add(
        NewsArticle(
            asset_id=a.id,
            url_hash="cd" * 32,
            title="t",
            url="https://example.com/a",
            published_at=datetime.now(UTC),
        )
    )
    session.commit()
    session.add(
        NewsArticle(
            asset_id=a.id,
            url_hash="cd" * 32,
            title="t2",
            url="https://example.com/a2",
            published_at=datetime.now(UTC),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_duplicate_market_price_rejected(session):
    a = _asset(session)
    session.add(
        MarketPrice(
            asset_id=a.id,
            provider="twelve_data",
            trade_date=date(2026, 11, 2),
            close=500.0,
        )
    )
    session.commit()
    session.add(
        MarketPrice(
            asset_id=a.id,
            provider="twelve_data",
            trade_date=date(2026, 11, 2),
            close=501.0,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_duplicate_collection_job_dedupe_key_rejected(session):
    session.add(CollectionJob(dedupe_key="collect:0700:2026-11-02", job_type="collect"))
    session.commit()
    session.add(CollectionJob(dedupe_key="collect:0700:2026-11-02", job_type="collect"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_duplicate_sentiment_result_rejected(session):
    session.add(
        SentimentResult(item_type="social_post", item_id=1, model_name="m1", label="positive")
    )
    session.commit()
    session.add(
        SentimentResult(item_type="social_post", item_id=1, model_name="m1", label="neutral")
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_duplicate_prediction_rejected(session):
    a = _asset(session)
    session.add(
        Prediction(
            asset_id=a.id,
            model_version="v1",
            target_date=date(2026, 11, 3),
            predicted_return=0.01,
            predicted_price=505.0,
        )
    )
    session.commit()
    session.add(
        Prediction(
            asset_id=a.id,
            model_version="v1",
            target_date=date(2026, 11, 3),
            predicted_return=0.02,
            predicted_price=506.0,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


# --- UTC rule: naive timestamps rejected, aware accepted -------------------
def test_naive_published_at_rejected(session):
    a = _asset(session)
    p = SocialPost(
        asset_id=a.id,
        source="facebook",
        content_hash="ef" * 32,
        content="post",
        published_at=datetime(2026, 11, 1, 12, 0, 0),  # NAIVE
    )
    session.add(p)
    # UTCDateTime rejects naive datetimes at bind time; SQLAlchemy surfaces the
    # underlying ValueError wrapped in a StatementError.
    with pytest.raises(StatementError) as excinfo:
        session.commit()
    assert isinstance(excinfo.value.__cause__, ValueError)
    assert "naive" in str(excinfo.value.__cause__)
    session.rollback()


def test_aware_utc_accepted(session):
    a = _asset(session)
    p = SocialPost(
        asset_id=a.id,
        source="facebook",
        content_hash="12" * 32,
        content="post",
        published_at=datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC),
    )
    session.add(p)
    session.commit()
    assert p.id is not None


# --- missing data stays NULL, never 0 --------------------------------------
def test_missing_engagement_is_null(session):
    a = _asset(session)
    p = SocialPost(
        asset_id=a.id,
        source="linkedin",
        content_hash="34" * 32,
        content="post",
        published_at=datetime.now(UTC),
    )
    session.add(p)
    session.commit()
    assert p.engagement is None


def test_prediction_actual_close_stays_null_until_backfill(session):
    a = _asset(session)
    pred = Prediction(
        asset_id=a.id,
        model_version="v1",
        target_date=date(2026, 11, 3),
        predicted_return=0.005,
        predicted_price=502.5,
    )
    session.add(pred)
    session.commit()
    assert pred.actual_close is None


# --- check constraints -------------------------------------------------------
def test_bad_job_status_rejected(session):
    session.add(CollectionJob(dedupe_key="k1", job_type="collect", status="bogus"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_bad_sentiment_item_type_rejected(session):
    session.add(
        SentimentResult(item_type="blog", item_id=9, model_name="m", label="positive")
    )
    with pytest.raises(IntegrityError):
        session.commit()


# --- seed loader invents nothing -------------------------------------------
def test_seed_loader_empty_config_seeds_nothing(session, monkeypatch, tmp_path):
    from app.scripts import seed_assets

    cfg = tmp_path / "empty.json"
    cfg.write_text('{"assets": []}')
    Session = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    added = seed_assets.seed(Session, str(cfg))
    assert added == 0
    assert session.execute(select(func.count(Asset.id))).scalar_one() == 0


def test_seed_loader_seeds_pending_confirmed_false(session, tmp_path):
    from app.scripts import seed_assets

    cfg = tmp_path / "seed.json"
    cfg.write_text(
        '{"assets": [{"exchange": "HKEX", "ticker": "9988", "name": "Alibaba", '
        '"provider_ticker": "9988.HK"}]}'
    )
    Session = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    added = seed_assets.seed(Session, str(cfg))
    assert added == 1
    row = session.execute(
        select(Asset).where(Asset.ticker == "9988")
    ).scalar_one()
    assert row.confirmed is False  # seeded pending, never silently confirmed


def test_seed_loader_missing_config_file_seeds_nothing(session, tmp_path):
    from app.scripts import seed_assets

    Session = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    assert seed_assets.seed(Session, str(tmp_path / "does_not_exist.json")) == 0
