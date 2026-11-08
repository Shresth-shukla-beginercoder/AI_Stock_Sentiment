"""Idempotent persistence for collected market / news / social data.

PostgreSQL ``INSERT ... ON CONFLICT DO NOTHING`` upserts keyed on the
dedupe constraints:

- market_prices: (asset_id, trade_date, provider)
- news_articles: (url_hash)
- social_posts:  (source, content_hash)

Guarantees (CLAUDE.md data rules):
- A duplicate key is a **no-op**, never an overwrite — re-running collection
  cannot duplicate or clobber valid rows.
- Missing values stay NULL, never 0.
- ``created_at`` is set by the Postgres ``now()`` server default (UTC); we never
  pass local time.
- ``published_at`` is NOT NULL in the schema; when a source has no publication
  timestamp we fall back to the collection instant and *report the count* so the
  fallback is transparent, not hidden.
- Schema is never changed here (no new columns / tables).

All functions take an active SQLAlchemy ``Session`` (caller controls commit /
rollback) and run inside the caller's transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select, and_
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
    synthetic_timestamps: int = 0  # records that fell back to collection time


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


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def persist_market_prices(
    session: Session,
    asset_id: int,
    provider: str,
    rows: list[PriceRow],
    *,
    is_demo: bool = False,
) -> PersistResult:
    """Upsert daily OHLCV bars. trade_date is stored as the UTC calendar date.

    ``inserted``/``skipped`` come from a pre-insert existence query (Postgres
    does not report a reliable rowcount for ``ON CONFLICT DO NOTHING``).
    """
    now = _utc_now()
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
            "created_at": now,
        }
    payload = list(by_date.values())
    if not payload:
        return PersistResult(provider, 0, 0, 0)

    dates = [p["trade_date"] for p in payload]
    existing = session.execute(
        select(MarketPrice.trade_date).where(
            and_(
                MarketPrice.asset_id == asset_id,
                MarketPrice.provider == provider,
                MarketPrice.trade_date.in_(dates),
            )
        )
    ).scalars().all()
    existing_set = set(existing)
    new_rows = [p for p in payload if p["trade_date"] not in existing_set]
    inserted = len(new_rows)
    skipped = len(payload) - inserted

    stmt = (
        pg_insert(MarketPrice)
        .values(new_rows)
        .on_conflict_do_nothing(index_elements=["asset_id", "trade_date", "provider"])
    )
    if new_rows:  # an all-duplicate batch must not emit "INSERT ... VALUES ()"
        session.execute(stmt)
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
    never coerced to a fake URL. Missing published_at -> collection instant.
    """
    now = _utc_now()
    payload = []
    synthetic = 0
    dropped = 0
    for it in items:
        if not it.url_hash:
            dropped += 1
            continue
        pub = it.published_at or now
        if it.published_at is None:
            synthetic += 1
        payload.append({
            "asset_id": asset_id,
            "source": it.source,
            "url_hash": it.url_hash,
            "title": it.title or "",  # title is NOT NULL; empty title is honest
            "body": it.body,
            "url": it.url,
            "published_at": pub,
            "is_demo": is_demo,
            "created_at": now,
        })
    if dropped:
        _log.warning("persist news: dropped records without URL/hash",
                     extra={"provider": "exa", "dropped": dropped})
    if not payload:
        return PersistResult("exa", 0, 0, synthetic)

    # Dedupe the batch by url_hash (first occurrence wins), then compute how
    # many are genuinely new vs already present.
    seen: set[str] = set()
    unique_payload = []
    for p in payload:
        if p["url_hash"] in seen:
            continue
        seen.add(p["url_hash"])
        unique_payload.append(p)

    existing = session.execute(
        select(NewsArticle.url_hash).where(
            NewsArticle.url_hash.in_([p["url_hash"] for p in unique_payload])
        )
    ).scalars().all()
    existing_set = set(existing)
    new_rows = [p for p in unique_payload if p["url_hash"] not in existing_set]
    inserted = len(new_rows)
    skipped = len(unique_payload) - inserted

    stmt = (
        pg_insert(NewsArticle)
        .values(new_rows)
        .on_conflict_do_nothing(index_elements=["url_hash"])
    )
    if new_rows:  # an all-duplicate batch must not emit "INSERT ... VALUES ()"
        session.execute(stmt)
    _log.info("persist news",
              extra={"asset_id": asset_id, "inserted": inserted,
                     "skipped_duplicates": skipped, "synthetic_timestamps": synthetic})
    return PersistResult("exa", inserted, skipped, synthetic)


def persist_social(
    session: Session,
    asset_id: int,
    items: list,
    *,
    is_demo: bool = False,
) -> PersistResult:
    """Upsert social candidates (SocialPostItem) keyed by (source, content_hash)."""
    now = _utc_now()
    payload = []
    synthetic = 0
    for it in items:
        if not it.content:
            continue  # a post with no discussion text is not kept
        pub = it.published_at or now
        if it.published_at is None:
            synthetic += 1
        payload.append({
            "asset_id": asset_id,
            "source": it.source,
            "content_hash": it.content_hash,
            "content": it.content,
            "language": it.language,
            "url": it.url,
            "published_at": pub,
            "engagement": it.engagement,  # NULL when unknown, never 0
            "is_demo": is_demo,
            "created_at": now,
        })
    if not payload:
        return PersistResult("apify", 0, 0, synthetic)

    # Dedupe the batch by (source, content_hash), first occurrence wins.
    seen: set[tuple] = set()
    unique_payload = []
    for p in payload:
        key = (p["source"], p["content_hash"])
        if key in seen:
            continue
        seen.add(key)
        unique_payload.append(p)

    existing_pairs = session.execute(
        select(SocialPost.source, SocialPost.content_hash).where(
            and_(
                SocialPost.source.in_([p["source"] for p in unique_payload]),
                SocialPost.content_hash.in_([p["content_hash"] for p in unique_payload]),
            )
        )
    ).all()
    existing_set = {(s, h) for (s, h) in existing_pairs}
    new_rows = [p for p in unique_payload
                if (p["source"], p["content_hash"]) not in existing_set]
    inserted = len(new_rows)
    skipped = len(unique_payload) - inserted

    stmt = (
        pg_insert(SocialPost)
        .values(new_rows)
        .on_conflict_do_nothing(index_elements=["source", "content_hash"])
    )
    if new_rows:  # an all-duplicate batch must not emit "INSERT ... VALUES ()"
        session.execute(stmt)
    _log.info("persist social",
              extra={"asset_id": asset_id, "inserted": inserted,
                     "skipped_duplicates": skipped, "synthetic_timestamps": synthetic})
    return PersistResult("apify", inserted, skipped, synthetic)
