"""Actual-close backfill for predictions (W6).

A prediction row's ``actual_close`` stays NULL until the target session has
been traded and a matching ``market_prices`` bar exists. This service fills
those NULLs from the real stored close for that session — so a model's OOS
performance can be compared against the CORRECT realized price, never against
an assumed one.

- Only predictions with ``actual_close IS NULL`` are touched (idempotent).
- Only sessions whose target_date is in the past relative to ``as_of`` and
  for which at least one provider stored a close are updated; anything else
  stays NULL and is counted, never guessed.
- Provider choice: the asset's configured provider if present, else the most
  recent bar for that session (ties broken by created_at).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Asset, MarketPrice, Prediction
from app.core.logging import get_logger

_log = get_logger("services.predict_backfill")


@dataclass
class BackfillResult:
    considered: int = 0        # predictions in scope (NULL actual_close, due date)
    updated: int = 0           # actual_close filled from a stored bar
    no_price_yet: int = 0      # due, but no stored close yet — stays NULL
    future: int = 0            # target session not yet traded — untouched


def backfill_actual_closes(
    session: Session,
    *,
    model_version: Optional[str] = None,
    as_of: Optional[datetime] = None,
) -> BackfillResult:
    """Fill NULL ``actual_close`` values from stored market-price bars."""
    res = BackfillResult()
    as_of = as_of or datetime.now(timezone.utc)
    q = select(Prediction).where(Prediction.actual_close.is_(None))
    if model_version:
        q = q.where(Prediction.model_version == model_version)
    preds = session.execute(q).scalars().all()

    for p in preds:
        if p.target_date >= as_of.date():
            res.future += 1
            continue
        res.considered += 1

        asset = session.get(Asset, p.asset_id)
        bars = session.execute(
            select(MarketPrice)
            .where(
                MarketPrice.asset_id == p.asset_id,
                MarketPrice.trade_date == p.target_date,
                MarketPrice.close.is_not(None),
            )
            .order_by(MarketPrice.created_at.desc())
        ).scalars().all()
        if not bars:
            res.no_price_yet += 1
            continue
        preferred = next(
            (b for b in bars if asset and b.provider == asset.market_data_provider),
            bars[0],
        )
        p.actual_close = float(preferred.close)
        res.updated += 1

    if res.updated:
        session.flush()
    _log.info(
        "actual-close backfill",
        extra={"considered": res.considered, "updated": res.updated,
               "no_price_yet": res.no_price_yet, "future": res.future},
    )
    return res
