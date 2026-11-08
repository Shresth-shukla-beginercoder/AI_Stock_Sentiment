"""Phase 5 correction 2: Concurrent-safe persistence tests.

Verifies that ON CONFLICT DO NOTHING backed by unique constraints prevents
duplicate inserts when multiple collectors run simultaneously.
"""
import pytest
from datetime import datetime, timezone
from sqlalchemy import select, delete
from app.database.session import get_session_factory
from app.database.models import Asset, NewsArticle, SocialPost
from app.services.persist import persist_news, persist_social
from app.collectors.exa import NewsItem
from app.collectors.apify import SocialPostItem
from app.collectors.normalize import url_hash, social_content_hash, parse_timestamp


def _wipe_concurrent_test_data():
    """Idempotent cleanup for P5C test asset and its specific test rows."""
    factory = get_session_factory()
    with factory() as s:
        try:
            # Delete specific test rows by their unique keys
            test_url_hashes = [
                url_hash("https://example.org/concurrent1"),
                url_hash("https://example.org/no-date"),
            ]
            s.execute(delete(NewsArticle).where(NewsArticle.url_hash.in_(test_url_hashes)))

            test_content_hash = social_content_hash("telegram", "concurrent text", "c1")
            test_content_hash2 = social_content_hash("telegram", "no date post", "nd1")
            s.execute(delete(SocialPost).where(
                SocialPost.content_hash.in_([test_content_hash, test_content_hash2])
            ))

            # Delete test asset (CASCADE will handle any remaining children)
            s.execute(delete(Asset).where(Asset.ticker == "P5C"))
            s.commit()
        except Exception:
            s.rollback()


@pytest.fixture(scope="function")
def concurrent_test_asset():
    """Create test asset P5C, yield its id, then clean up."""
    _wipe_concurrent_test_data()  # clean any leftover from crashed runs
    factory = get_session_factory()
    with factory() as s:
        a = Asset(exchange="P5X", ticker="P5C", name="P5 concurrent", confirmed=True)
        s.add(a)
        s.commit()
        s.refresh(a)
        asset_id = a.id
    yield asset_id
    _wipe_concurrent_test_data()


def test_persist_news_concurrent_safety(concurrent_test_asset):
    """Two sessions insert the same news item; ON CONFLICT ensures only one succeeds."""
    factory = get_session_factory()
    asset_id = concurrent_test_asset

    uh = url_hash("https://example.org/concurrent1")
    item1 = NewsItem(
        url="https://example.org/concurrent1",
        url_hash=uh,
        title="Concurrent Test",
        body="Body",
        published_at=parse_timestamp("2026-01-01T00:00:00Z"),
        author="a",
        source="example.org",
        external_id="c1",
        content_hash=uh,
    )
    item2 = NewsItem(
        url="https://example.org/concurrent1",
        url_hash=uh,
        title="Concurrent Test",
        body="Body",
        published_at=parse_timestamp("2026-01-01T00:00:00Z"),
        author="a",
        source="example.org",
        external_id="c1",
        content_hash=uh,
    )

    # Simulate concurrency: two different sessions persist the same item
    with factory() as s1:
        r1 = persist_news(s1, asset_id, [item1])
        s1.commit()

    with factory() as s2:
        r2 = persist_news(s2, asset_id, [item2])
        s2.commit()

    # First insert succeeds, second skips due to conflict
    assert r1.inserted == 1 and r1.skipped_duplicates == 0
    assert r2.inserted == 0 and r2.skipped_duplicates == 1

    # Verify only one row exists
    with factory() as s:
        count = s.execute(
            select(NewsArticle).where(NewsArticle.url_hash == uh)
        ).scalars().all()
        assert len(count) == 1


def test_persist_social_concurrent_safety(concurrent_test_asset):
    """Two sessions insert the same social post; ON CONFLICT ensures only one succeeds."""
    factory = get_session_factory()
    asset_id = concurrent_test_asset

    ch = social_content_hash("telegram", "concurrent text", "c1")
    item1 = SocialPostItem(
        source="telegram",
        content_hash=ch,
        content="concurrent text",
        url=None,
        published_at=parse_timestamp("2026-01-01T00:00:00Z"),
        engagement=5,
        external_id="c1",
        author_id="a1",
        language="en",
    )
    item2 = SocialPostItem(
        source="telegram",
        content_hash=ch,
        content="concurrent text",
        url=None,
        published_at=parse_timestamp("2026-01-01T00:00:00Z"),
        engagement=5,
        external_id="c1",
        author_id="a1",
        language="en",
    )

    # Simulate concurrency: two different sessions persist the same item
    with factory() as s1:
        r1 = persist_social(s1, asset_id, [item1])
        s1.commit()

    with factory() as s2:
        r2 = persist_social(s2, asset_id, [item2])
        s2.commit()

    # First insert succeeds, second skips due to conflict
    assert r1.inserted == 1 and r1.skipped_duplicates == 0
    assert r2.inserted == 0 and r2.skipped_duplicates == 1

    # Verify only one row exists
    with factory() as s:
        count = s.execute(
            select(SocialPost).where(
                SocialPost.source == "telegram",
                SocialPost.content_hash == ch
            )
        ).scalars().all()
        assert len(count) == 1


def test_persist_news_null_published_at(concurrent_test_asset):
    """News item with no published_at persists as NULL, not substituted."""
    factory = get_session_factory()
    asset_id = concurrent_test_asset

    uh = url_hash("https://example.org/no-date")
    item = NewsItem(
        url="https://example.org/no-date",
        url_hash=uh,
        title="No Date",
        body=None,
        published_at=None,  # Missing publication timestamp
        author=None,
        source="example.org",
        external_id="nd1",
        content_hash=uh,
    )

    with factory() as s:
        r = persist_news(s, asset_id, [item])
        s.commit()
        assert r.inserted == 1
        assert r.null_published_at == 1

        # Verify published_at is NULL in DB
        article = s.execute(
            select(NewsArticle).where(NewsArticle.url_hash == uh)
        ).scalar_one()
        assert article.published_at is None  # NULL, not collection time
        assert article.created_at is not None  # Collection time in created_at


def test_persist_social_null_published_at(concurrent_test_asset):
    """Social post with no published_at persists as NULL, not substituted."""
    factory = get_session_factory()
    asset_id = concurrent_test_asset

    ch = social_content_hash("telegram", "no date post", "nd1")
    item = SocialPostItem(
        source="telegram",
        content_hash=ch,
        content="no date post",
        url=None,
        published_at=None,  # Missing publication timestamp
        engagement=None,
        external_id="nd1",
        author_id=None,
        language=None,
    )

    with factory() as s:
        r = persist_social(s, asset_id, [item])
        s.commit()
        assert r.inserted == 1
        assert r.null_published_at == 1

        # Verify published_at is NULL in DB
        post = s.execute(
            select(SocialPost).where(
                SocialPost.source == "telegram",
                SocialPost.content_hash == ch
            )
        ).scalar_one()
        assert post.published_at is None  # NULL, not collection time
        assert post.created_at is not None  # Collection time in created_at
