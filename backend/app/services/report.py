"""Per-ticker, exchange-separated report (W5).

Both exchanges are reported separately. Every ticker row carries the same
fields in demo and live mode (the API and the frontend represent the SAME
report data):

- ``ticker`` / ``name`` — identity
- ``current_price`` — the latest stored bar ``{close, provider, trade_date}``,
  or ``null`` when no bar has been stored yet
- ``sentiment`` — ``{score, signal, state}`` from the settings-wired
  aggregation (thresholds + min-items from config, never hard-coded)
- ``direction`` — sign of the asset's LATEST stored prediction's
  ``predicted_return``: ``up`` / ``down`` / ``flat`` / ``none``
- ``prediction`` — the full latest prediction row (or ``null``)
- ``support_resistance`` — W4 window-extremes levels (``data_sufficient``
  distinguishes missing levels from a price that genuinely sits there)
- ``position`` — where ``current_price.close`` sits relative to the levels:
  ``above_resistance`` / ``between`` / ``below_support`` / ``unknown``
- ``mentions`` — ``{social_posts, news_articles, total}``; a zero here means
  zero rows were stored, while ``null`` upstream fields mean "not yet known"

Ranking within each exchange (deterministic, documented in ``meta``):
total mentions desc → sentiment score desc (None last) → ticker asc.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.models import (
    Asset,
    MarketPrice,
    NewsArticle,
    Prediction,
    SocialPost,
)
from app.features.sessions import exchange_tz_name
from app.features.support_resistance import levels_to_dict, support_resistance
from app.core.logging import get_logger
from app.services import store

_log = get_logger("services.report")


# ---------------------------------------------------------------------------
# field builders (each returns null when the data genuinely does not exist)
# ---------------------------------------------------------------------------
def _latest_price(session: Session, asset_id: int) -> Optional[dict[str, Any]]:
    row = session.execute(
        select(MarketPrice)
        .where(MarketPrice.asset_id == asset_id)
        .order_by(MarketPrice.trade_date.desc(), MarketPrice.created_at.desc())
        .limit(1)
    ).scalars().first()
    if row is None:
        return None
    return {
        "close": float(row.close) if row.close is not None else None,
        "provider": row.provider,
        "trade_date": row.trade_date.isoformat(),
    }


def _latest_prediction(session: Session, asset_id: int) -> Optional[dict[str, Any]]:
    row = session.execute(
        select(Prediction)
        .where(Prediction.asset_id == asset_id)
        .order_by(Prediction.target_date.desc(), Prediction.id.desc())
        .limit(1)
    ).scalars().first()
    if row is None:
        return None
    pred_ret = float(row.predicted_return) if row.predicted_return is not None else None
    if pred_ret is None:
        direction = "none"
    elif pred_ret > 0:
        direction = "up"
    elif pred_ret < 0:
        direction = "down"
    else:
        direction = "flat"
    return {
        "model_version": row.model_version,
        "target_date": row.target_date.isoformat(),
        "predicted_return": pred_ret,
        "predicted_price": float(row.predicted_price) if row.predicted_price is not None else None,
        "actual_close": float(row.actual_close) if row.actual_close is not None else None,
        "experimental": row.experimental,
        "direction": direction,
    }


def _mention_counts(session: Session, asset_id: int) -> dict[str, int]:
    social = session.execute(
        select(func.count()).select_from(SocialPost).where(SocialPost.asset_id == asset_id)
    ).scalar_one()
    news = session.execute(
        select(func.count()).select_from(NewsArticle).where(NewsArticle.asset_id == asset_id)
    ).scalar_one()
    return {"social_posts": social, "news_articles": news, "total": social + news}


def _position(close: Optional[float], sr: dict[str, Any]) -> str:
    """Honest position of the current close vs the stored S/R levels."""
    if close is None or not sr.get("data_sufficient"):
        return "unknown"
    support, resistance = sr.get("support"), sr.get("resistance")
    if support is None or resistance is None:
        return "unknown"
    if close > resistance:
        return "above_resistance"
    if close < support:
        return "below_support"
    return "between"


def _ticker_row(session: Session, asset: Asset, settings) -> dict[str, Any]:
    sentiment = store.sentiment_for_ticker(session, asset.ticker)
    sr = levels_to_dict(
        support_resistance(
            session,
            asset.id,
            window_sessions=settings.support_resistance_window_sessions,
        )
    )
    price = _latest_price(session, asset.id)
    prediction = _latest_prediction(session, asset.id)
    direction = prediction["direction"] if prediction else "none"
    close = price["close"] if price else None
    return {
        "ticker": asset.ticker,
        "name": asset.name,
        "current_price": price,
        "sentiment": {
            "score": sentiment["score"],
            "signal": sentiment["signal"],
            "state": sentiment["state"],
        },
        "direction": direction,
        "prediction": prediction,
        "support_resistance": sr,
        "position": _position(close, sr),
        "mentions": _mention_counts(session, asset.id),
        "is_demo": False,
    }


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
def build_ticker_report(session: Session, settings=None) -> dict[str, Any]:
    """Build the exchange-separated per-ticker report (live mode)."""
    settings = settings or get_settings()
    assets = session.execute(
        select(Asset).order_by(Asset.exchange, Asset.ticker)
    ).scalars().all()

    by_exchange: dict[str, list[dict[str, Any]]] = {}
    for a in assets:
        by_exchange.setdefault(a.exchange or "UNKNOWN", []).append(_ticker_row(session, a, settings))

    exchanges = []
    for ex in sorted(by_exchange):
        rows = sorted(
            by_exchange[ex],
            key=lambda r: (
                -r["mentions"]["total"],
                r["sentiment"]["score"] is None,
                -(r["sentiment"]["score"] or 0.0),
                r["ticker"],
            ),
        )
        for i, r in enumerate(rows, 1):
            r["rank"] = i
        exchanges.append({
            "exchange": ex,
            "timezone": exchange_tz_name(ex),
            "tickers": rows,
        })

    ranking = [r for ex in exchanges for r in ex["tickers"]]
    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "exchanges": exchanges,
        "ranking": ranking,
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "ranking_rule": "total mentions desc, then sentiment score desc (None last), then ticker asc — within each exchange",
            "sentiment_thresholds": {
                "bullish": settings.sentiment_threshold_bullish,
                "bearish": settings.sentiment_threshold_bearish,
                "min_items": settings.sentiment_min_items,
                "window_days": settings.sentiment_window_days,
            },
            "support_resistance_window_sessions": settings.support_resistance_window_sessions,
            "direction_rule": "sign of the latest stored prediction's predicted_return",
            "missing_policy": "null = not yet known / no data stored; 0 = a real count of zero",
        },
    }


__all__ = [
    "build_ticker_report",
    "levels_to_dict",
    "support_resistance",
]
