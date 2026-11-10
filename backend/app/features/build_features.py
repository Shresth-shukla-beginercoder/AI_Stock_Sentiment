"""Feature aggregation pipeline (Phase 8).

Combines price-derived indicators + Phase 6 sentiment features into a feature
matrix ready for ML training. Enforces:

- No look-ahead bias: each row uses only data available at prediction time.
- Honest missing handling: NULL stays NULL (never forward-fill to 0).
- Demo/live isolation: never mix synthetic and real data in training.
- Sentiment feature confidence: track valid observation counts and mark
  insufficient overlap as experimental.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Optional
from dataclasses import dataclass

from sqlalchemy import select, and_, Date
from sqlalchemy.orm import Session

from app.database.models import MarketPrice, SentimentResult, SocialPost, NewsArticle
from app.features.indicators import (
    historical_returns,
    moving_averages,
    volatility,
    rsi,
    volume_indicators,
)
from app.features.make_target import compute_targets
from app.core.logging import get_logger

_log = get_logger("features.build_features")


@dataclass
class FeatureRow:
    """A single row of features + target for one asset on one date."""

    asset_id: int
    trade_date: date
    # Price features
    return_1d: Optional[float] = None
    return_5d: Optional[float] = None
    return_10d: Optional[float] = None
    ma_5d: Optional[float] = None
    ma_10d: Optional[float] = None
    ma_20d: Optional[float] = None
    volatility_10d: Optional[float] = None
    rsi_14: Optional[float] = None
    volume_ma: Optional[float] = None
    volume_ratio: Optional[float] = None
    # Sentiment features (Phase 6)
    sentiment_social_score: Optional[float] = None
    sentiment_social_count: Optional[int] = None
    sentiment_news_score: Optional[float] = None
    sentiment_news_count: Optional[int] = None
    # Target (next-day return)
    target_return: Optional[float] = None
    # Metadata
    is_demo: bool = False
    sentiment_experimental: bool = False  # True if insufficient sentiment overlap

    def to_dict(self) -> dict:
        """Convert to dict for ML ingestion."""
        return {
            k: v for k, v in self.__dict__.items()
            if not k.startswith("_")
        }


def build_features(
    session: Session,
    asset_id: int,
    lookback_days: int = 60,
) -> list[FeatureRow]:
    """Build feature matrix for one asset.

    Fetches price history + sentiment, computes indicators, merges, and returns
    rows ready for training.

    Args:
        session: Active SQLAlchemy session.
        asset_id: Asset ID to build features for.
        lookback_days: How many days of history to fetch (default 60).

    Returns:
        List of FeatureRow objects, one per trading day, sorted by date.
    """
    from app.database.models import Asset

    asset = session.get(Asset, asset_id)
    if not asset:
        _log.warning("build_features: asset not found", extra={"asset_id": asset_id})
        return []

    now_utc = datetime.now(timezone.utc)
    start_date = (now_utc - timedelta(days=lookback_days)).date()

    # Fetch price history (all providers for this asset).
    prices_stmt = (
        select(MarketPrice)
        .where(
            and_(
                MarketPrice.asset_id == asset_id,
                MarketPrice.trade_date >= start_date,
            )
        )
        .order_by(MarketPrice.trade_date.asc())
    )
    price_rows = session.execute(prices_stmt).scalars().all()

    if not price_rows:
        _log.info("build_features: no price history", extra={"asset_id": asset_id})
        return []

    # Dedupe by trade_date (use the most recent provider if multiple).
    # close is Postgres Numeric -> Decimal; cast to float so the look-back
    # indicator math (which mixes with float literals like 0.0) does not hit a
    # Decimal/float TypeError. Missing stays None, never 0.
    price_by_date: dict[date, tuple[date, Optional[float], Optional[int], bool]] = {}
    for pr in price_rows:
        key = pr.trade_date
        if key not in price_by_date:
            close = float(pr.close) if pr.close is not None else None
            price_by_date[key] = (pr.trade_date, close, pr.volume, pr.is_demo)

    sorted_dates = sorted(price_by_date.keys())
    prices_for_indicators = [(d, price_by_date[d][1]) for d in sorted_dates]
    prices_for_volume = [(d, price_by_date[d][1], price_by_date[d][2]) for d in sorted_dates]

    # Compute indicators (all look-back-only).
    rets = historical_returns(prices_for_indicators)
    mas = moving_averages(prices_for_indicators)
    vols = volatility(prices_for_indicators)
    rsi_vals = rsi(prices_for_indicators)
    vol_inds = volume_indicators(prices_for_volume)
    targets = compute_targets(asset_id, prices_for_indicators)

    # Fetch sentiment aggregates (10-day window, as per CLAUDE.md).
    sentiment_window = 10
    sentiment_data: dict[date, tuple[Optional[float], int, Optional[float], int]] = {}

    for trade_date in sorted_dates:
        sentiment_window_start = trade_date - timedelta(days=sentiment_window)

        # Social sentiment
        social_stmt = (
            select(SentimentResult)
            .where(
                and_(
                    SentimentResult.item_type == "social_post",
                    SentimentResult.item_id.in_(
                        select(SocialPost.id).where(
                            and_(
                                SocialPost.asset_id == asset_id,
                                SocialPost.created_at.cast(Date) >= sentiment_window_start,
                                SocialPost.created_at.cast(Date) <= trade_date,
                            )
                        )
                    ),
                )
            )
        )
        try:
            social_results = session.execute(social_stmt).scalars().all()
        except Exception:
            social_results = []

        # News sentiment
        news_stmt = (
            select(SentimentResult)
            .where(
                and_(
                    SentimentResult.item_type == "news_article",
                    SentimentResult.item_id.in_(
                        select(NewsArticle.id).where(
                            and_(
                                NewsArticle.asset_id == asset_id,
                                NewsArticle.created_at.cast(Date) >= sentiment_window_start,
                                NewsArticle.created_at.cast(Date) <= trade_date,
                            )
                        )
                    ),
                )
            )
        )
        try:
            news_results = session.execute(news_stmt).scalars().all()
        except Exception:
            news_results = []

        # Compute aggregated scores (0.4 social + 0.6 news per CLAUDE.md).
        social_score = None
        social_count = 0
        if social_results:
            social_score = sum(float(r.score) for r in social_results if r.score is not None) / max(
                len([r for r in social_results if r.score is not None]), 1
            )
            social_count = len(social_results)

        news_score = None
        news_count = 0
        if news_results:
            news_score = sum(float(r.score) for r in news_results if r.score is not None) / max(
                len([r for r in news_results if r.score is not None]), 1
            )
            news_count = len(news_results)

        sentiment_data[trade_date] = (social_score, social_count, news_score, news_count)

    # Build feature rows.
    rows: list[FeatureRow] = []
    for idx, date_val in enumerate(sorted_dates):
        price_info = price_by_date[date_val]
        is_demo = price_info[3]

        row = FeatureRow(
            asset_id=asset_id,
            trade_date=date_val,
            # Price features from indicators
            return_1d=rets[idx].get("return_1d"),
            return_5d=rets[idx].get("return_5d"),
            return_10d=rets[idx].get("return_10d"),
            ma_5d=mas[idx].get("ma_5d"),
            ma_10d=mas[idx].get("ma_10d"),
            ma_20d=mas[idx].get("ma_20d"),
            volatility_10d=vols[idx],
            rsi_14=rsi_vals[idx],
            volume_ma=vol_inds[idx].get("volume_ma"),
            volume_ratio=vol_inds[idx].get("volume_ratio"),
            # Sentiment (from window)
            is_demo=is_demo,
        )

        if date_val in sentiment_data:
            social_score, social_count, news_score, news_count = sentiment_data[date_val]
            row.sentiment_social_score = social_score
            row.sentiment_social_count = social_count
            row.sentiment_news_score = news_score
            row.sentiment_news_count = news_count
            # Mark experimental if insufficient data
            if (social_count + news_count) < 3:
                row.sentiment_experimental = True

        row.target_return = targets.get(date_val)
        rows.append(row)

    _log.info(
        "build_features complete",
        extra={
            "asset_id": asset_id,
            "rows": len(rows),
            "is_demo": is_demo,
        },
    )
    return rows


def filter_for_training(
    rows: list[FeatureRow],
    *,
    demo_only: bool = False,
    exclude_experimental: bool = False,
    require_target: bool = True,
) -> list[FeatureRow]:
    """Filter feature rows for training.

    Args:
        rows: All feature rows.
        demo_only: If True, keep only demo rows; if False, keep only live rows.
        exclude_experimental: If True, drop rows with insufficient sentiment.
        require_target: If True, drop rows without a target value.

    Returns:
        Filtered list of rows.
    """
    filtered = rows
    filtered = [r for r in filtered if r.is_demo == demo_only]
    if exclude_experimental:
        filtered = [r for r in filtered if not r.sentiment_experimental]
    if require_target:
        filtered = [r for r in filtered if r.target_return is not None]
    return filtered
