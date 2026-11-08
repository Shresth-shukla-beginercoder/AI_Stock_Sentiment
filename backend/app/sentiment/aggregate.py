"""Sentiment aggregation by asset and trading session (Phase 6).

Combines social posts + news articles using configurable weights.
Engagement weighting: 1 + ln(1 + engagement)
Per-asset/trading-date aggregation with explicit insufficient_data handling.
"""

from typing import Optional
from datetime import date, datetime, timezone
from dataclasses import dataclass
import math

from sqlalchemy import select, and_, func, cast, Date
from sqlalchemy.orm import Session

from app.database.models import Asset, SentimentResult, SocialPost, NewsArticle
from app.core.config import get_settings
from app.core.logging import get_logger

_log = get_logger("sentiment.aggregate")


def _session_date_col(model) -> object:
    """COALESCE(published_at, created_at) cast to DATE, for session-date grouping.

    Phase 5 correction 1 made published_at nullable: when a source had no
    publication time, created_at (the collection instant) is the fallback. Both
    are UTC timestamptz, so the calendar date is the UTC session date.
    """
    return cast(
        func.coalesce(model.published_at, model.created_at), Date
    )


@dataclass
class AggregatedSentiment:
    """Per-asset, per-session-date aggregated sentiment."""
    asset_id: int
    session_date: date
    label: str  # positive, neutral, negative, or insufficient_data
    score: Optional[float]  # weighted average or None
    social_count: int
    news_count: int
    total_items: int
    social_weight: float
    news_weight: float
    model_id: str


def _engagement_weight(engagement: Optional[int]) -> float:
    """Calculate engagement weight: 1 + ln(1 + engagement).

    Missing engagement is treated as 0.
    """
    e = max(0, engagement or 0)  # Ensure non-negative
    return 1.0 + math.log(1.0 + e)


def aggregate_sentiment_for_asset(
    session: Session,
    asset_id: int,
    session_date: date,
) -> Optional[AggregatedSentiment]:
    """Aggregate sentiment results for an asset on a specific trading date.

    Combines:
    - Social posts (weight 0.4)
    - News articles (weight 0.6)

    Engagement weighting: 1 + ln(1 + engagement)

    Returns None if no sentiment results exist (no collection yet).
    Returns insufficient_data if < 5 total items (configurable threshold).
    """
    settings = get_settings()

    # Query sentiment results for social posts on this asset/date
    social_results = session.execute(
        select(SentimentResult, SocialPost).where(
            and_(
                SentimentResult.item_type == "social_post",
                SentimentResult.item_id == SocialPost.id,
                SocialPost.asset_id == asset_id,
                # Filter by publishing date (or created_at if published_at is NULL)
                func.date(func.coalesce(SocialPost.published_at, SocialPost.created_at)) == session_date,
            )
        )
    ).all()

    # Query sentiment results for news articles on this asset/date
    news_results = session.execute(
        select(SentimentResult, NewsArticle).where(
            and_(
                SentimentResult.item_type == "news_article",
                SentimentResult.item_id == NewsArticle.id,
                NewsArticle.asset_id == asset_id,
                # Filter by publishing date (or created_at if published_at is NULL)
                func.date(func.coalesce(NewsArticle.published_at, NewsArticle.created_at)) == session_date,
            )
        )
    ).all()

    social_count = len(social_results)
    news_count = len(news_results)
    total_items = social_count + news_count

    if total_items == 0:
        return None  # No data collected yet

    if total_items < settings.sentiment_min_items:
        _log.debug("insufficient data for aggregation",
                   extra={"asset_id": asset_id, "date": session_date,
                          "total": total_items, "min": settings.sentiment_min_items})
        return AggregatedSentiment(
            asset_id=asset_id,
            session_date=session_date,
            label="insufficient_data",
            score=None,
            social_count=social_count,
            news_count=news_count,
            total_items=total_items,
            social_weight=settings.sentiment_social_weight,
            news_weight=settings.sentiment_news_weight,
            model_id="(aggregated)",
        )

    # Calculate weighted sentiment score
    social_scores = []
    for sent_result, post in social_results:
        if sent_result.score is not None:
            weight = _engagement_weight(post.engagement)
            social_scores.append((sent_result.score, weight))

    news_scores = []
    for sent_result, article in news_results:
        if sent_result.score is not None:
            # News has no engagement field; weight is always 1.0
            weight = 1.0
            news_scores.append((sent_result.score, weight))

    if not social_scores and not news_scores:
        return AggregatedSentiment(
            asset_id=asset_id,
            session_date=session_date,
            label="insufficient_data",
            score=None,
            social_count=social_count,
            news_count=news_count,
            total_items=total_items,
            social_weight=settings.sentiment_social_weight,
            news_weight=settings.sentiment_news_weight,
            model_id="(aggregated)",
        )

    # Weighted average per source
    social_weighted_avg = None
    if social_scores:
        weighted_sum = sum(score * weight for score, weight in social_scores)
        total_weight = sum(weight for _, weight in social_scores)
        social_weighted_avg = weighted_sum / total_weight if total_weight > 0 else 0.0

    news_weighted_avg = None
    if news_scores:
        weighted_sum = sum(score * weight for score, weight in news_scores)
        total_weight = sum(weight for _, weight in news_scores)
        news_weighted_avg = weighted_sum / total_weight if total_weight > 0 else 0.0

    # Combined score: 0.4 social + 0.6 news
    combined_score = None
    if social_weighted_avg is not None and news_weighted_avg is not None:
        combined_score = (
            settings.sentiment_social_weight * social_weighted_avg +
            settings.sentiment_news_weight * news_weighted_avg
        )
    elif social_weighted_avg is not None:
        combined_score = social_weighted_avg  # Only social data
    elif news_weighted_avg is not None:
        combined_score = news_weighted_avg  # Only news data

    # Determine label
    if combined_score is not None:
        if combined_score > settings.sentiment_threshold_bullish:
            label = "positive"
        elif combined_score < settings.sentiment_threshold_bearish:
            label = "negative"
        else:
            label = "neutral"
        combined_score = round(combined_score, 6)
    else:
        label = "insufficient_data"

    return AggregatedSentiment(
        asset_id=asset_id,
        session_date=session_date,
        label=label,
        score=combined_score,
        social_count=social_count,
        news_count=news_count,
        total_items=total_items,
        social_weight=settings.sentiment_social_weight,
        news_weight=settings.sentiment_news_weight,
        model_id="(aggregated)",
    )
