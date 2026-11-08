"""Concurrent-safe persistence of sentiment results (Phase 6).

Uses PostgreSQL ON CONFLICT DO NOTHING backed by unique constraint
(item_type, item_id, model_name) to prevent duplicate scoring.
"""

from dataclasses import dataclass
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database.models import SentimentResult
from app.core.logging import get_logger

_log = get_logger("sentiment.persist")


@dataclass
class PersistResult:
    """Counts for sentiment result persistence (safe to log)."""
    inserted: int
    skipped_duplicates: int


def persist_sentiment_result(
    session: Session,
    item_type: str,
    item_id: int,
    model_name: str,
    label: str,
    score: float,
    p_pos: float,
    p_neu: float,
    p_neg: float,
) -> PersistResult:
    """Persist a sentiment result (social post or news article).

    Concurrent-safe: ON CONFLICT DO NOTHING backed by unique constraint
    (item_type, item_id, model_name). Duplicate attempts skip silently.

    Args:
        session: SQLAlchemy session (caller controls commit/rollback)
        item_type: "social_post" or "news_article"
        item_id: PK of SocialPost or NewsArticle
        model_name: Hugging Face model ID or "(aggregated)"
        label: "positive", "neutral", "negative", or "insufficient_data"
        score: P(pos) - P(neg), or None if insufficient_data
        p_pos, p_neu, p_neg: probabilities

    Returns:
        PersistResult with inserted and skipped counts.
    """
    stmt = (
        pg_insert(SentimentResult)
        .values(
            item_type=item_type,
            item_id=item_id,
            model_name=model_name,
            label=label,
            score=score,
            p_pos=p_pos,
            p_neu=p_neu,
            p_neg=p_neg,
        )
        .on_conflict_do_nothing(
            index_elements=["item_type", "item_id", "model_name"]
        )
        .returning(SentimentResult.id)
    )
    result = session.execute(stmt)
    inserted = len(result.fetchall())
    skipped = 1 - inserted  # Either 0 or 1

    _log.info("persist sentiment result",
              extra={
                  "item_type": item_type,
                  "item_id": item_id,
                  "model_name": model_name,
                  "label": label,
                  "inserted": inserted,
                  "skipped": skipped,
              })
    return PersistResult(inserted, skipped)
