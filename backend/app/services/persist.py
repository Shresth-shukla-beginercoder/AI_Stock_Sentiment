"""Idempotent persistence for collected market / news / social data.

PostgreSQL ``INSERT ... ON CONFLICT DO NOTHING`` upserts keyed on the
dedupe constraints:

- market_prices: (asset_id, trade_date, provider)
- news_articles: (url_hash)
- social_posts:  (source, content_hash)

Guarantees (CLAUDE.md data rules + Phase 5 corrections):
- A duplicate key is a **no-op**, never an overwrite — re-running collection
  cannot duplicate or clobber valid rows.
- Missing values stay NULL, never 0.
- ``created_at`` is set by the Postgres ``now()`` server default (UTC); we never
  pass local time. This is the collection timestamp.
- ``published_at`` is **nullable** (Phase 5 correction 1): when a source has no
  publication timestamp we preserve NULL honestly, never substitute collection
  time. Downstream consumers distinguish unknown (NULL) from known (timestamp).
- Schema is never changed here (no new columns / tables).
- **Concurrent-safe** (Phase 5 correction 2): Uses ``ON CONFLICT DO NOTHING``
  backed by unique constraints; no pre-query race. ``RETURNING *`` gives
  actually-inserted rows for accurate counts.

All functions take an active SQLAlchemy ``Session`` (caller controls commit /
rollback) and run inside the caller's transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.collectors.provider import PriceRow
from app.database.models import Asset, MarketPrice, NewsArticle, SocialPost
from app.core.logging import get_logger
from sqlalchemy.orm import Session

_log = get_logger("services.persist")


@dataclass
class PersistResult:
    """Counts for one persistence call (safe to log)."""

    provider: str
    inserted: int
    skipped_duplicates: int
    null_published_at: int = 0  # records with no source publication timestamp


def resolve_asset(session: Session, ticker: str,
                  exchange: Optional[str] = None) -> Optional[Asset]:
    """Find the asset row a collected record attaches to.

    Matches provider_ticker first, then the raw ticker (same as services/store).
    Returns None when no asset row exists — callers must then *not* persist
    (never fabricate an asset, never seed a pending ticker as confirmed).
    """
    q = select(Asset).where(Asset.provider_ticker == ticker)
    asset = session.execute(q).scalar_one_or_none()
    if asset is None:
        q = select(Asset).where(Asset.ticker == ticker)
        if exchange:
            q = q.where(Asset.exchange == exchange)
        asset = session.execute(q).scalar_one_or_none()
    return asset


def persist_market_prices(
    session: Session,
    asset_id: int,
    provider: str,
    rows: list[PriceRow],
    *,
    is_demo: bool = False,
) -> PersistResult:
    """Upsert daily OHLCV bars. trade_date is stored as the UTC calendar date.

    Concurrent-safe: ``ON CONFLICT DO NOTHING`` backed by the unique constraint
    on (asset_id, trade_date, provider). ``RETURNING *`` gives actually-inserted
    rows for accurate counts (no race with other collectors).
    """
    # One row per trading day: dedupe the batch by date (latest bar wins).
    by_date: dict[date, dict] = {}
    for r in rows:
        d = r.trade_date.date() if isinstance(r.trade_date, datetime) else r.trade_date
        by_date[d] = {
            "asset_id": asset_id,
            "provider": provider,
            "trade_date": d,
            "open": r.open,
            "high": r.high,
            "low": r.low,
            "close": r.close,
            "volume": r.volume,
            "is_demo": is_demo,
            # created_at omitted → Postgres server default now()
        }
    payload = list(by_date.values())
    if not payload:
        return PersistResult(provider, 0, 0, 0)

    stmt = (
        pg_insert(MarketPrice)
        .values(payload)
        .on_conflict_do_nothing(index_elements=["asset_id", "trade_date", "provider"])
        .returning(MarketPrice.id)
    )
    result = session.execute(stmt)
    inserted = len(result.fetchall())
    skipped = len(payload) - inserted

    _log.info("persist market prices",
              extra={"provider": provider, "asset_id": asset_id,
                     "inserted": inserted, "skipped_duplicates": skipped})
    return PersistResult(provider, inserted, skipped, 0)


def persist_news(
    session: Session,
    asset_id: Optional[int],
    items: list,
    *,
    is_demo: bool = False,
) -> PersistResult:
    """Upsert news candidates (NewsItem) keyed by url_hash.

    Items without a URL (and therefore no url_hash) are dropped with a log line,
    never coerced to a fake URL. Missing published_at → NULL (Phase 5 correction 1).

    Concurrent-safe: ``ON CONFLICT DO NOTHING`` backed by the unique constraint
    on (url_hash). ``RETURNING *`` gives actually-inserted rows.
    """
    payload = []
    null_published = 0
    dropped = 0
    for it in items:
        if not it.url_hash:
            dropped += 1
            continue
        if it.published_at is None:
            null_published += 1
        payload.append({
            "asset_id": asset_id,
            "source": it.source,
            "url_hash": it.url_hash,
            "title": it.title or "",  # title is NOT NULL; empty title is honest
            "body": it.body,
            "url": it.url,
            "published_at": it.published_at,  # NULL stays NULL (Phase 5 correction)
            "is_demo": is_demo,
            # created_at omitted → Postgres server default now()
        })
    if dropped:
        _log.warning("persist news: dropped records without URL/hash",
                     extra={"provider": "exa", "dropped": dropped})
    if not payload:
        return PersistResult("exa", 0, 0, null_published)

    # Dedupe the batch by url_hash (first occurrence wins).
    seen: set[str] = set()
    unique_payload = []
    for p in payload:
        if p["url_hash"] in seen:
            continue
        seen.add(p["url_hash"])
        unique_payload.append(p)

    stmt = (
        pg_insert(NewsArticle)
        .values(unique_payload)
        .on_conflict_do_nothing(index_elements=["url_hash"])
        .returning(NewsArticle.id)
    )
    result = session.execute(stmt)
    inserted = len(result.fetchall())
    skipped = len(unique_payload) - inserted

    _log.info("persist news",
              extra={"asset_id": asset_id, "inserted": inserted,
                     "skipped_duplicates": skipped, "null_published_at": null_published})
    return PersistResult("exa", inserted, skipped, null_published)


def persist_social(
    session: Session,
    asset_id: int,
    items: list,
    *,
    is_demo: bool = False,
) -> PersistResult:
    """Upsert social candidates (SocialPostItem) keyed by (source, content_hash).

    Missing published_at → NULL (Phase 5 correction 1), never substituted with
    collection time. Concurrent-safe via ``ON CONFLICT DO NOTHING``.
    """
    payload = []
    null_published = 0
    for it in items:
        if not it.content:
            continue  # a post with no discussion text is not kept
        if it.published_at is None:
            null_published += 1
        payload.append({
            "asset_id": asset_id,
            "source": it.source,
            "content_hash": it.content_hash,
            "content": it.content,
            "language": it.language,
            "url": it.url,
            "published_at": it.published_at,  # NULL stays NULL (Phase 5 correction)
            "engagement": it.engagement,  # NULL when unknown, never 0
            "is_demo": is_demo,
            # created_at omitted → Postgres server default now()
        })
    if not payload:
        return PersistResult("apify", 0, 0, null_published)

    # Dedupe the batch by (source, content_hash), first occurrence wins.
    seen: set[tuple] = set()
    unique_payload = []
    for p in payload:
        key = (p["source"], p["content_hash"])
        if key in seen:
            continue
        seen.add(key)
        unique_payload.append(p)

    stmt = (
        pg_insert(SocialPost)
        .values(unique_payload)
        .on_conflict_do_nothing(index_elements=["source", "content_hash"])
        .returning(SocialPost.id)
    )
    result = session.execute(stmt)
    inserted = len(result.fetchall())
    skipped = len(unique_payload) - inserted

    _log.info("persist social",
              extra={"asset_id": asset_id, "inserted": inserted,
                     "skipped_duplicates": skipped, "null_published_at": null_published})
    return PersistResult("apify", inserted, skipped, null_published)
