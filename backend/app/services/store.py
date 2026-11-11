"""Read access to live (database) data.

Used only when DATA_MODE=live. Honest states: empty results return
``state: "no_data"`` — collectors/ML fill these tables in Phases 5–8, so an
empty DB is expected today, and we never fabricate live rows.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import or_, select, func
from sqlalchemy.orm import Session

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


def _match_asset(session: Session, ticker: str) -> Asset | None:
    """Resolve an asset by either identifier (NULL-safe).

    A row carries two identifiers of the same asset: the raw ``ticker``
    (e.g. ``"1810"``) and the vendor ``provider_ticker`` (e.g. ``"1810.HK"``).
    Both must resolve to the row — the list endpoint surfaces the raw ticker,
    so the detail/subresource lookups must accept it even when
    ``provider_ticker`` is set. A NULL ``provider_ticker`` simply fails its
    branch and the raw ticker still matches (never COALESCE: that made the
    raw ticker unresolvable whenever the vendor symbol was present).
    """
    q = select(Asset).where(or_(Asset.ticker == ticker, Asset.provider_ticker == ticker))
    return session.execute(q).scalars().first()


def asset_or_none(session: Session, ticker: str) -> Asset | None:
    return _match_asset(session, ticker)


def asset_dict(a: Asset) -> dict[str, Any]:
    return {
        "exchange": a.exchange,
        "ticker": a.ticker,
        "name": a.name,
        "provider_ticker": a.provider_ticker,
        "provider_symbol_format": a.provider_symbol_format,
        "market_data_provider": a.market_data_provider,
        "confirmed": a.confirmed,
        "active": a.active,
        "is_demo": False,
    }


def list_assets(session: Session) -> list[dict[str, Any]]:
    rows = session.execute(select(Asset).order_by(Asset.exchange, Asset.ticker)).scalars().all()
    return [asset_dict(a) for a in rows]


def _asset_ids(session: Session, ticker: str) -> list[int]:
    a = _match_asset(session, ticker)
    return [a.id] if a else []


def list_posts(session: Session, ticker: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    ids = _asset_ids(session, ticker)
    if not ids:
        return [], 0
    q = (
        select(SocialPost)
        .where(SocialPost.asset_id.in_(ids))
        .order_by(SocialPost.published_at.desc())
        .limit(limit)
        .offset(offset)
    )
    total = session.execute(
        select(func.count()).select_from(SocialPost).where(SocialPost.asset_id.in_(ids))
    ).scalar_one()
    rows = session.execute(q).scalars().all()
    return [
        {
            "id": p.id,
            "asset_ticker": ticker,
            "source": p.source,
            "content_hash": p.content_hash,
            "content": p.content,
            "language": p.language,
            "url": p.url,
            "published_at": p.published_at.isoformat() if p.published_at else None,
            "engagement": p.engagement,  # NULL stays NULL
            "is_demo": p.is_demo,
        }
        for p in rows
    ], total


def list_news(session: Session, ticker: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    ids = _asset_ids(session, ticker)
    if not ids:
        return [], 0
    q = (
        select(NewsArticle)
        .where(NewsArticle.asset_id.in_(ids))
        .order_by(NewsArticle.published_at.desc())
        .limit(limit)
        .offset(offset)
    )
    total = session.execute(
        select(func.count()).select_from(NewsArticle).where(NewsArticle.asset_id.in_(ids))
    ).scalar_one()
    rows = session.execute(q).scalars().all()
    return [
        {
            "id": n.id,
            "asset_ticker": ticker,
            "source": n.source,
            "url_hash": n.url_hash,
            "title": n.title,
            "body": n.body,
            "url": n.url,
            "published_at": n.published_at.isoformat() if n.published_at else None,
            "is_demo": n.is_demo,
        }
        for n in rows
    ], total


def list_prices(session: Session, ticker: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    ids = _asset_ids(session, ticker)
    if not ids:
        return [], 0
    q = (
        select(MarketPrice)
        .where(MarketPrice.asset_id.in_(ids))
        .order_by(MarketPrice.trade_date.desc())
        .limit(limit)
        .offset(offset)
    )
    total = session.execute(
        select(func.count()).select_from(MarketPrice).where(MarketPrice.asset_id.in_(ids))
    ).scalar_one()
    rows = session.execute(q).scalars().all()
    return [
        {
            "id": r.id,
            "asset_ticker": ticker,
            "provider": r.provider,
            "trade_date": r.trade_date.isoformat(),
            "open": float(r.open) if r.open is not None else None,
            "high": float(r.high) if r.high is not None else None,
            "low": float(r.low) if r.low is not None else None,
            "close": float(r.close) if r.close is not None else None,
            "volume": r.volume,
            "is_demo": r.is_demo,
        }
        for r in rows
    ], total


def sentiment_for_ticker(session: Session, ticker: str) -> dict[str, Any]:
    """Sentiment aggregate for one ticker, wired to settings (W5/W7).

    Thresholds, min-items and window come from config — never hard-coded —
    so a config change flows through to every consumer (ranking, reports,
    dashboard).
    """
    from app.core.config import get_settings
    settings = get_settings()
    ids = _asset_ids(session, ticker)
    base: dict[str, Any] = {
        "asset_ticker": ticker,
        "window_days": settings.sentiment_window_days,
        "as_of": datetime.now(timezone.utc).isoformat(),
        "state": "no_data",
        "counts": {"positive": 0, "neutral": 0, "negative": 0},
        "total_items": 0,
        "p_pos": None,
        "p_neu": None,
        "p_neg": None,
        "score": None,
        "signal": None,
    }
    if not ids:
        return base
    posts = session.execute(
        select(SentimentResult).where(
            SentimentResult.item_type == "social_post",
            SentimentResult.item_id.in_(
                select(SocialPost.id).where(SocialPost.asset_id.in_(ids))
            ),
        )
    ).scalars().all()
    news = session.execute(
        select(SentimentResult).where(
            SentimentResult.item_type == "news_article",
            SentimentResult.item_id.in_(
                select(NewsArticle.id).where(NewsArticle.asset_id.in_(ids))
            ),
        )
    ).scalars().all()
    results = list(posts) + list(news)
    if not results:
        return base
    counts = {"positive": 0, "neutral": 0, "negative": 0}
    for r in results:
        counts[r.label] = counts.get(r.label, 0) + 1
    total = len(results)
    p_pos = counts["positive"] / total
    p_neu = counts["neutral"] / total
    p_neg = counts["negative"] / total
    score = round(p_pos - p_neg, 6)
    base.update(
        {
            "state": "sufficient" if total >= settings.sentiment_min_items else "insufficient_data",
            "counts": counts,
            "total_items": total,
            "p_pos": round(p_pos, 6),
            "p_neu": round(p_neu, 6),
            "p_neg": round(p_neg, 6),
            "score": score,
            "signal": (
                "positive" if score > settings.sentiment_threshold_bullish
                else "negative" if score < settings.sentiment_threshold_bearish
                else "neutral"
            ),
        }
    )
    return base


def list_predictions(session: Session, ticker: str, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    ids = _asset_ids(session, ticker)
    if not ids:
        return [], 0
    q = (
        select(Prediction)
        .where(Prediction.asset_id.in_(ids))
        .order_by(Prediction.target_date.desc())
        .limit(limit)
        .offset(offset)
    )
    total = session.execute(
        select(func.count()).select_from(Prediction).where(Prediction.asset_id.in_(ids))
    ).scalar_one()
    rows = session.execute(q).scalars().all()
    return [
        {
            "id": p.id,
            "asset_ticker": ticker,
            "model_version": p.model_version,
            "target_date": p.target_date.isoformat(),
            "made_at": p.made_at.isoformat() if p.made_at else None,
            "predicted_return": float(p.predicted_return) if p.predicted_return is not None else None,
            "predicted_price": float(p.predicted_price) if p.predicted_price is not None else None,
            "actual_close": float(p.actual_close) if p.actual_close is not None else None,
            "experimental": p.experimental,
        }
        for p in rows
    ], total


def list_evaluations(session: Session, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    q = (
        select(ModelEvaluation)
        .order_by(ModelEvaluation.trained_at.desc())
        .limit(limit)
        .offset(offset)
    )
    total = session.execute(select(func.count()).select_from(ModelEvaluation)).scalar_one()
    rows = session.execute(q).scalars().all()
    return [
        {
            "id": e.id,
            "model_version": e.model_version,
            "mae": float(e.mae) if e.mae is not None else None,
            "rmse": float(e.rmse) if e.rmse is not None else None,
            "directional_accuracy": float(e.directional_accuracy) if e.directional_accuracy is not None else None,
            "baseline_nochange_mae": float(e.baseline_nochange_mae) if e.baseline_nochange_mae is not None else None,
            "baseline_nochange_rmse": float(e.baseline_nochange_rmse) if e.baseline_nochange_rmse is not None else None,
            "baseline_nochange_dir_acc": float(e.baseline_nochange_dir_acc) if e.baseline_nochange_dir_acc is not None else None,
            "baseline_alwaysup_dir_acc": float(e.baseline_alwaysup_dir_acc) if e.baseline_alwaysup_dir_acc is not None else None,
            "n_test": e.n_test,
            "params": e.params,
            "git_commit": e.git_commit,
            "trained_at": e.trained_at.isoformat() if e.trained_at else None,
        }
        for e in rows
    ], total


def model_versions(session: Session) -> list[str]:
    rows = session.execute(
        select(ModelEvaluation.model_version).order_by(ModelEvaluation.model_version)
    ).scalars().all()
    return list(rows)


def overview(session: Session) -> dict[str, Any]:
    n_assets = session.execute(select(func.count()).select_from(Asset)).scalar_one()
    n_posts = session.execute(select(func.count()).select_from(SocialPost)).scalar_one()
    n_news = session.execute(select(func.count()).select_from(NewsArticle)).scalar_one()
    n_prices = session.execute(select(func.count()).select_from(MarketPrice)).scalar_one()
    n_preds = session.execute(select(func.count()).select_from(Prediction)).scalar_one()
    n_models = session.execute(select(func.count()).select_from(ModelEvaluation)).scalar_one()

    # W5 parity: the live overview carries the same per_ticker shape as the
    # demo overview (name, posts, news, price_days, sentiment_score,
    # sentiment_signal, state) — the dashboard relies on it in both modes.
    post_counts = dict(
        session.execute(select(SocialPost.asset_id, func.count()).group_by(SocialPost.asset_id)).all()
    )
    news_counts = dict(
        session.execute(select(NewsArticle.asset_id, func.count()).group_by(NewsArticle.asset_id)).all()
    )
    price_counts = dict(
        session.execute(select(MarketPrice.asset_id, func.count()).group_by(MarketPrice.asset_id)).all()
    )
    per_ticker: dict[str, Any] = {}
    for a in session.execute(select(Asset).order_by(Asset.exchange, Asset.ticker)).scalars():
        s = sentiment_for_ticker(session, a.ticker)
        per_ticker[a.ticker] = {
            "name": a.name,
            "posts": post_counts.get(a.id, 0),
            "news": news_counts.get(a.id, 0),
            "price_days": price_counts.get(a.id, 0),
            "sentiment_score": s["score"],
            "sentiment_signal": s["signal"],
            "state": s["state"],
        }

    return {
        "universe": [a["ticker"] for a in list_assets(session)],
        "per_ticker": per_ticker,
        "counts": {
            "assets": n_assets,
            "social_posts": n_posts,
            "news_articles": n_news,
            "market_prices": n_prices,
            "predictions": n_preds,
            "model_versions": n_models,
        },
        "state": "no_data" if n_posts + n_news + n_prices + n_preds == 0 else "ok",
        "note": "Live counts from the database — may be empty until collection and training jobs have run.",
    }


def ranking(session: Session) -> list[dict[str, Any]]:
    out = []
    for a in session.execute(select(Asset).order_by(Asset.exchange, Asset.ticker)).scalars():
        s = sentiment_for_ticker(session, a.ticker)
        out.append({"ticker": a.ticker, "name": a.name, "score": s["score"], "state": s["state"]})
    out.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0)))
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


# --- jobs (persistent queue; workers arrive in Phase 7) -----------------------
def list_jobs(session: Session, limit: int, offset: int) -> tuple[list[dict[str, Any]], int]:
    total = session.execute(select(func.count()).select_from(CollectionJob)).scalar_one()
    rows = (
        session.execute(
            select(CollectionJob).order_by(CollectionJob.id.desc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": j.id,
            "job_type": j.job_type,
            "status": j.status,
            "dedupe_key": j.dedupe_key,
            "params": j.params,
            "attempts": j.attempts,
            "max_attempts": j.max_attempts,
            "error": j.error,
            "claimed_by": j.claimed_by,
            "claimed_at": j.claimed_at.isoformat() if j.claimed_at else None,
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "updated_at": j.updated_at.isoformat() if j.updated_at else None,
        }
        for j in rows
    ], total


def job_or_none(session: Session, job_id: int) -> dict[str, Any] | None:
    j = session.get(CollectionJob, job_id)
    if j is None:
        return None
    return {
        "id": j.id,
        "job_type": j.job_type,
        "status": j.status,
        "dedupe_key": j.dedupe_key,
        "params": j.params,
        "attempts": j.attempts,
        "max_attempts": j.max_attempts,
        "error": j.error,
        "claimed_by": j.claimed_by,
        "claimed_at": j.claimed_at.isoformat() if j.claimed_at else None,
        "created_at": j.created_at.isoformat() if j.created_at else None,
        "updated_at": j.updated_at.isoformat() if j.updated_at else None,
    }


def queue_job(
    session: Session, *, job_type: str, dedupe_key: str, params: dict[str, Any]
) -> tuple[CollectionJob, bool]:
    """Insert a queued job. Returns (job, created). Duplicate dedupe_key -> (existing, False)."""
    existing = session.execute(
        select(CollectionJob).where(CollectionJob.dedupe_key == dedupe_key)
    ).scalars().first()
    if existing is not None:
        return existing, False
    job = CollectionJob(dedupe_key=dedupe_key, job_type=job_type, status="queued", params=params)
    session.add(job)
    session.commit()
    session.refresh(job)
    return job, True


def today_utc() -> date:
    return datetime.now(timezone.utc).date()
