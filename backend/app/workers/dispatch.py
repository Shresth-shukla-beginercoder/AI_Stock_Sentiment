"""Job dispatcher: routes jobs to appropriate handlers (Phase 7).

Handlers connect to Phase 5 collectors and Phase 6 sentiment pipeline.
"""

from typing import Optional, Dict, Any
from datetime import datetime, date

from sqlalchemy.orm import Session

from app.database.models import CollectionJob
from app.core.logging import get_logger
from app.core.config import get_settings

_log = get_logger("workers.dispatch")


def handle_collect_market(session: Session, job: CollectionJob) -> Dict[str, Any]:
    """Handle collect:market job - fetch daily price data."""
    from app.collectors.provider import get_daily_prices

    params = job.params or {}
    ticker = params["ticker"]
    target_date = date.fromisoformat(params["target_date"])

    # Fetch price data for the target date
    # For daily data, fetch a small window around the target date
    start_date = target_date
    end_date = target_date

    _log.info("collecting market data", extra={"ticker": ticker, "date": target_date.isoformat()})

    result = get_daily_prices(ticker, start_date, end_date)

    return {
        "source": result.source,
        "fetched": result.count,
        "inserted": result.inserted,
        "skipped_duplicates": result.skipped_duplicates,
    }


def handle_collect_social(session: Session, job: CollectionJob) -> Dict[str, Any]:
    """Handle collect:social job - fetch social media posts."""
    from app.collectors.apify import collect_social_posts

    params = job.params or {}
    asset_id = params["asset_id"]
    ticker = params["ticker"]
    target_date = date.fromisoformat(params["target_date"])

    _log.info("collecting social posts", extra={"ticker": ticker, "date": target_date.isoformat()})

    result = collect_social_posts(session, asset_id, ticker, target_date)

    return {
        "source": result.source,
        "fetched": result.count,
        "inserted": result.inserted,
        "skipped_duplicates": result.skipped_duplicates,
    }


def handle_collect_news(session: Session, job: CollectionJob) -> Dict[str, Any]:
    """Handle collect:news job - fetch news articles."""
    from app.collectors.exa import collect_news_articles

    params = job.params or {}
    asset_id = params["asset_id"]
    ticker = params["ticker"]
    target_date = date.fromisoformat(params["target_date"])

    _log.info("collecting news articles", extra={"ticker": ticker, "date": target_date.isoformat()})

    result = collect_news_articles(session, asset_id, ticker, target_date)

    return {
        "source": result.source,
        "fetched": result.count,
        "inserted": result.inserted,
        "skipped_duplicates": result.skipped_duplicates,
    }


def handle_score_sentiment(session: Session, job: CollectionJob) -> Dict[str, Any]:
    """Handle score:sentiment job - analyze sentiment for collected posts/articles."""
    from app.sentiment import (
        preprocess_for_sentiment,
        select_model,
        analyze,
        persist_sentiment_result,
    )
    from app.database.models import SocialPost, NewsArticle
    from sqlalchemy import select, and_, func

    params = job.params or {}
    asset_id = params["asset_id"]
    ticker = params["ticker"]
    session_date = date.fromisoformat(params["session_date"])

    _log.info("scoring sentiment", extra={"ticker": ticker, "date": session_date.isoformat()})

    # Fetch all social posts for this asset/date that don't have sentiment yet
    social_stmt = (
        select(SocialPost)
        .where(
            and_(
                SocialPost.asset_id == asset_id,
                func.date(func.coalesce(SocialPost.published_at, SocialPost.created_at)) == session_date,
            )
        )
        .outerjoin(
            # LEFT JOIN to find posts without sentiment results
            # Note: This is a simplified check; in production, you'd check for specific model_name
            select(1).select_from(SocialPost).correlate(SocialPost).scalar_subquery()
        )
    )
    social_posts = session.execute(social_stmt).scalars().all()

    # Fetch all news articles for this asset/date that don't have sentiment yet
    news_stmt = (
        select(NewsArticle)
        .where(
            and_(
                NewsArticle.asset_id == asset_id,
                func.date(func.coalesce(NewsArticle.published_at, NewsArticle.created_at)) == session_date,
            )
        )
    )
    news_articles = session.execute(news_stmt).scalars().all()

    social_scored = 0
    news_scored = 0
    social_skipped = 0
    news_skipped = 0

    # Score social posts
    for post in social_posts:
        text = preprocess_for_sentiment(post.content)
        if not text:
            social_skipped += 1
            continue

        model_id = select_model(text, "social")
        if not model_id:
            social_skipped += 1
            continue

        score = analyze(text, model_id)
        if not score:
            social_skipped += 1
            continue

        # Persist sentiment result
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

    # Score news articles
    for article in news_articles:
        text = preprocess_for_sentiment(article.content)
        if not text:
            news_skipped += 1
            continue

        model_id = select_model(text, "news")
        if not model_id:
            news_skipped += 1
            continue

        score = analyze(text, model_id)
        if not score:
            news_skipped += 1
            continue

        # Persist sentiment result
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
    "collect:social": handle_collect_social,
    "collect:news": handle_collect_news,
    "score:sentiment": handle_score_sentiment,
}


def dispatch_job(session: Session, job: CollectionJob) -> Dict[str, Any]:
    """Dispatch a job to its handler.

    Returns a counts dictionary on success.
    Raises an exception on failure (caller handles retry logic).
    """
    handler = HANDLERS.get(job.job_type)

    if handler is None:
        raise ValueError(f"Unknown job type: {job.job_type}")

    _log.debug("dispatching job", extra={"job_id": job.id, "job_type": job.job_type})

    return handler(session, job)
