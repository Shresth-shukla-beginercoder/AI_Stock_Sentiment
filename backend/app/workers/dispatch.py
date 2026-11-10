"""Job dispatcher: routes jobs to appropriate handlers (Phase 7).

Handlers connect to Phase 5 collectors and Phase 6 sentiment pipeline.
"""

from typing import Optional, Dict, Any
from datetime import datetime, date

from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session

from app.database.models import CollectionJob
from app.core.logging import get_logger
from app.core.config import get_settings
from app.workers.exceptions import UnsupportedJobError

_log = get_logger("workers.dispatch")


def handle_collect_market(session: Session, job: CollectionJob) -> Dict[str, Any]:
    """Handle collect:market job - fetch daily prices via the provider chain.

    Phase 14: the owner-selected primary provider (Twelve Data) runs first; a
    keyless yfinance fallback is tried when the primary errors or returns no
    bars (HKEX plan-gate 404 / KRX 429). Rows are persisted under the
    provider that actually produced them, preserving per-row attribution.
    """
    from app.collectors.chain import market_provider_chain, fetch_daily_prices
    from app.services.persist import resolve_asset, persist_market_prices

    settings = get_settings()
    params = job.params or {}
    ticker = params.get("ticker")
    if not ticker:
        raise ValueError("collect:market requires params['ticker']")
    target_date = date.fromisoformat(params["target_date"])

    # Fetch price data for the target date.
    # For daily data, fetch a small window around the target date.
    start_date = target_date
    end_date = target_date
    exchange = params.get("exchange")

    _log.info("collecting market data",
              extra={"ticker": ticker, "date": target_date.isoformat()})

    chain = market_provider_chain(settings, ticker, start_date, end_date, exchange=exchange)
    provider, rows, attempts = fetch_daily_prices(chain)

    asset = resolve_asset(session, ticker, exchange)
    if asset is None:
        # Honest: never fabricate an asset. Log and report zero counts.
        _log.warning("collect:market: asset not resolved; skipping persistence",
                     extra={"ticker": ticker})
        return {
            "provider": provider.provider_name,
            "fetched": len(rows),
            "inserted": 0,
            "skipped_duplicates": 0,
            "asset_resolved": False,
            "chain": attempts,
        }

    result = persist_market_prices(session, asset.id, provider.provider_name, rows)
    session.commit()

    return {
        "provider": provider.provider_name,
        "fetched": len(rows),
        "inserted": result.inserted,
        "skipped_duplicates": result.skipped_duplicates,
        "asset_resolved": True,
        "chain": attempts,
    }


def handle_backfill_market(session: Session, job: CollectionJob) -> Dict[str, Any]:
    """Handle a backfill:market job - fetch + persist ONE chunk of history.

    Phase A1: the historical window is pre-chunked at enqueue time (one job per
    chunk, dedupe_key ``backfill:market:{ticker}:{start}:{end}``), so this
    handler fetches a single chunk - sized to stay under the provider's
    per-call bar cap - and persists it under the provider that actually
    produced the rows (primary Twelve Data, else yfinance fallback).

    The chunk fetch is wrapped in ``bounded_retry`` so a yfinance rate limit
    (429) or transport fault retries with backoff rather than failing the job.
    Persistence is ``ON CONFLICT DO NOTHING`` on (asset_id, trade_date,
    provider), so re-running a chunk never duplicates or overwrites existing
    bars. Regular daily ``collect:market`` behaviour is untouched.
    """
    from app.collectors.chain import market_provider_chain, fetch_daily_prices
    from app.collectors.retry import bounded_retry
    from app.services.persist import resolve_asset, persist_market_prices

    settings = get_settings()
    params = job.params or {}
    ticker = params.get("ticker")
    start_iso = params.get("start")
    end_iso = params.get("end")
    if not (ticker and start_iso and end_iso):
        raise ValueError(
            "backfill:market requires params['ticker'], params['start'] and params['end']"
        )

    start = date.fromisoformat(start_iso)
    end = date.fromisoformat(end_iso)
    exchange = params.get("exchange")

    _log.info("backfilling market chunk",
              extra={"ticker": ticker, "start": start_iso, "end": end_iso})

    chain = market_provider_chain(settings, ticker, start, end, exchange=exchange)

    def _fetch():
        return fetch_daily_prices(chain)

    provider, rows, attempts = bounded_retry(_fetch, settings=settings)

    asset = resolve_asset(session, ticker, exchange)
    if asset is None:
        _log.warning("backfill:market: asset not resolved; skipping persistence",
                     extra={"ticker": ticker})
        return {
            "provider": provider.provider_name,
            "fetched": len(rows),
            "inserted": 0,
            "skipped_duplicates": 0,
            "asset_resolved": False,
            "window": [start_iso, end_iso],
            "chain": attempts,
        }

    result = persist_market_prices(session, asset.id, provider.provider_name, rows)
    session.commit()

    return {
        "provider": provider.provider_name,
        "fetched": len(rows),
        "inserted": result.inserted,
        "skipped_duplicates": result.skipped_duplicates,
        "asset_resolved": True,
        "window": [start_iso, end_iso],
        "chain": attempts,
    }


def handle_collect_social(session: Session, job: CollectionJob) -> Dict[str, Any]:
    """Handle collect:social job - fetch social media posts via Apify.

    The Apify candidate Actors are UNVERIFIED (see app/collectors/apify.py).
    This handler performs the read-only ``verify_actor`` step; it never runs an
    Actor unless the candidate was verified *and* the owner approved a run.
    """
    from app.collectors.apify import ApifySocialCollector, CANDIDATE_ACTORS

    settings = get_settings()
    params = job.params or {}
    ticker = params.get("ticker") or "unknown"
    target_date = date.fromisoformat(params["target_date"])

    _log.info("collecting social posts", extra={"ticker": ticker, "date": target_date.isoformat()})

    collector = ApifySocialCollector(settings=settings)

    # Verify each candidate (read-only, no run). Record outcomes; do not
    # silently replace or fabricate data.
    verify_results = []
    for candidate in CANDIDATE_ACTORS:
        try:
            availability = collector.verify_actor(candidate.ref, candidate.platform)
        except Exception as e:
            # Verification failed (auth/transport). Record honestly; do not raise.
            _log.warning("social actor verify failed",
                         extra={"actor": candidate.ref, "error": str(e)})
            verify_results.append({"actor": candidate.ref, "available": False,
                                  "reason": f"verify raised: {e}"})
            continue
        verify_results.append({
            "actor": candidate.ref,
            "available": availability.available,
            "reason": availability.reason,
        })

    # No actor is approved for running (Phase 5 boundary); we only record.
    _log.info("social collect: verification recorded, no runs approved",
              extra={"ticker": ticker, "actors": [v["actor"] for v in verify_results]})

    return {
        "provider": "apify",
        "fetched": 0,
        "inserted": 0,
        "skipped_duplicates": 0,
        "verifications": verify_results,
        "note": "actor runs not approved in Phase 5/7; verification recorded only",
    }


def handle_collect_news(session: Session, job: CollectionJob) -> Dict[str, Any]:
    """Handle collect:news job - fetch news articles via Exa."""
    from app.collectors.exa import ExaNewsCollector
    from app.services.persist import resolve_asset, persist_news

    settings = get_settings()
    params = job.params or {}
    ticker = params.get("ticker")
    if not ticker:
        raise ValueError("collect:news requires params['ticker']")
    ticker_name = params.get("ticker_name") or ticker
    target_date = date.fromisoformat(params["target_date"])

    _log.info("collecting news articles", extra={"ticker": ticker, "date": target_date.isoformat()})

    collector = ExaNewsCollector(settings=settings)
    query = f"{ticker_name} {ticker} news"
    items = collector.search(query, end=target_date)

    asset = resolve_asset(session, ticker, params.get("exchange"))
    if asset is None:
        _log.warning("collect:news: asset not resolved; skipping persistence",
                     extra={"ticker": ticker})
        return {
            "provider": "exa",
            "fetched": len(items),
            "inserted": 0,
            "skipped_duplicates": 0,
            "asset_resolved": False,
        }

    result = persist_news(session, asset.id, items)
    session.commit()

    return {
        "provider": "exa",
        "fetched": len(items),
        "inserted": result.inserted,
        "skipped_duplicates": result.skipped_duplicates,
        "null_published_at": result.null_published_at,
        "asset_resolved": True,
    }


def handle_score_sentiment(session: Session, job: CollectionJob) -> Dict[str, Any]:
    """Handle score:sentiment job - analyze sentiment for collected posts/articles.

    Uses Phase 6 pipeline (preprocess -> language routing -> model select ->
    analyze -> persist). Posts/articles that already have a result for the
    routed model are skipped via the unique (item_type, item_id, model_name)
    constraint so the job is idempotent.
    """
    from app.sentiment import (
        preprocess_for_sentiment,
        detect_language,
        select_model,
        analyze,
        persist_sentiment_result,
    )
    from app.database.models import SocialPost, NewsArticle

    params = job.params or {}
    asset_id = params.get("asset_id")
    ticker = params.get("ticker")
    session_date = date.fromisoformat(params["session_date"])

    _log.info("scoring sentiment", extra={"ticker": ticker, "date": session_date.isoformat()})

    # Fetch social posts for this asset/date (published_at or created_at day).
    social_posts = session.execute(
        select(SocialPost).where(
            and_(
                SocialPost.asset_id == asset_id,
                func.date(func.coalesce(SocialPost.published_at, SocialPost.created_at)) == session_date,
            )
        )
    ).scalars().all()

    # Fetch news articles for this asset/date.
    news_articles = session.execute(
        select(NewsArticle).where(
            and_(
                NewsArticle.asset_id == asset_id,
                func.date(func.coalesce(NewsArticle.published_at, NewsArticle.created_at)) == session_date,
            )
        )
    ).scalars().all()

    social_scored = 0
    news_scored = 0
    social_skipped = 0
    news_skipped = 0

    for post in social_posts:
        text = preprocess_for_sentiment(post.content)
        if not text:
            social_skipped += 1
            continue

        lang = detect_language(text)
        model_id = select_model(text, "social")
        if not model_id:
            # Language has no verified model (e.g. CJK) -> skip honestly.
            social_skipped += 1
            continue

        score = analyze(text, model_id)
        if score is None:
            social_skipped += 1
            continue

        persist_result = persist_sentiment_result(
            session,
            "social_post",
            post.id,
            score.model_id,
            score.label,
            score.score,
            score.p_pos,
            score.p_neu,
            score.p_neg,
        )
        if persist_result.inserted > 0:
            social_scored += 1

    for article in news_articles:
        text = preprocess_for_sentiment(article.body or article.title)
        if not text:
            news_skipped += 1
            continue

        model_id = select_model(text, "news")
        if not model_id:
            news_skipped += 1
            continue

        score = analyze(text, model_id)
        if score is None:
            news_skipped += 1
            continue

        persist_result = persist_sentiment_result(
            session,
            "news_article",
            article.id,
            score.model_id,
            score.label,
            score.score,
            score.p_pos,
            score.p_neu,
            score.p_neg,
        )
        if persist_result.inserted > 0:
            news_scored += 1

    session.commit()

    return {
        "social_posts_scored": social_scored,
        "social_posts_skipped": social_skipped,
        "news_articles_scored": news_scored,
        "news_articles_skipped": news_skipped,
        "total_scored": social_scored + news_scored,
    }


# Dispatcher registry
HANDLERS = {
    "collect:market": handle_collect_market,
    "backfill:market": handle_backfill_market,
    "collect:social": handle_collect_social,
    "collect:news": handle_collect_news,
    "score:sentiment": handle_score_sentiment,
}


def dispatch_job(session: Session, job: CollectionJob) -> Dict[str, Any]:
    """Dispatch a job to its handler.

    Returns a counts dictionary on success.
    Raises an exception on failure (caller handles retry logic).

    Unsupported types (train, unknown) raise :class:`UnsupportedJobError`;
    the worker marks them as permanent failures without retry.
    """
    handler = HANDLERS.get(job.job_type)

    if handler is None:
        reason = "handler_not_implemented_yet" if job.job_type == "train" else "unknown_job_type"
        raise UnsupportedJobError(job.job_type, reason, f"No handler registered for job type: {job.job_type}")

    _log.debug("dispatching job", extra={"job_id": job.id, "job_type": job.job_type})

    return handler(session, job)
