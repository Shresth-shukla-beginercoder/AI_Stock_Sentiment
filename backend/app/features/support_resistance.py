"""Per-ticker support / resistance from actual historical price bars (W4).

Methodology (transparent and reproducible):

- Input: the asset's real ``market_prices`` rows (any provider attribution;
  one bar per trading day).
- Window: the most recent ``window_sessions`` trading days (default 20,
  i.e. roughly one trading month), never more than what actually exists.
- ``support``    = the lowest  ``low``  in the window (a price the market has
  already defended inside the window).
- ``resistance`` = the highest  ``high`` in the window.
- If a window has fewer than 2 usable bars, or no usable low/high, the result
  is ``None`` with ``data_sufficient: False`` — insufficient history is
  reported, never filled with fabricated levels.

No indicator smoothing or machine-learned bands: the levels are a direct,
re-runnable summary of the stored bars, and the window size, method and
as-of date are returned with the result so any consumer can recompute them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import MarketPrice
from app.core.logging import get_logger

_log = get_logger("features.support_resistance")

DEFAULT_WINDOW_SESSIONS = 20
MIN_SESSIONS_FOR_LEVELS = 2


@dataclass
class Levels:
    """Per-asset support / resistance result."""

    support: Optional[float]
    resistance: Optional[float]
    method: str
    window_sessions: int          # requested window size
    available_sessions: int       # bars actually available (>= 2 usable -> sufficient)
    data_sufficient: bool
    as_of: Optional[date]         # most recent bar date the window ends on
    basis: str                    # provider attribution note


def support_resistance(
    session: Session,
    asset_id: int,
    *,
    window_sessions: int = DEFAULT_WINDOW_SESSIONS,
) -> Levels:
    """Compute support/resistance for one asset from its stored price bars."""
    if window_sessions < 1:
        window_sessions = 1

    rows = session.execute(
        select(MarketPrice)
        .where(MarketPrice.asset_id == asset_id)
        .order_by(MarketPrice.trade_date.desc())
        .limit(window_sessions)
    ).scalars().all()

    available = len(rows)
    usables = [r for r in rows if r.low is not None or r.high is not None]
    if available > 0 and usables:
        providers = sorted({r.provider for r in usables})
        basis = f"most recent {min(available, window_sessions)} stored bars (providers: {', '.join(providers)})"
    else:
        basis = "no usable stored bars"

    lows = [float(r.low) for r in usables if r.low is not None]
    highs = [float(r.high) for r in usables if r.high is not None]

    sufficient = len(usables) >= MIN_SESSIONS_FOR_LEVELS
    if not sufficient:
        # Documented rule: fewer than 2 usable bars -> no levels at all,
        # never a one-bar "extreme" dressed up as support/resistance.
        support = None
        resistance = None
    else:
        support = min(lows) if lows else None
        resistance = max(highs) if highs else None
    as_of = max(r.trade_date for r in rows) if rows else None

    if not sufficient:
        _log.info("support/resistance: insufficient history",
                  extra={"asset_id": asset_id, "available": available})

    return Levels(
        support=support,
        resistance=resistance,
        method="window_extremes: support=min(low), resistance=max(high) over the most recent "
               f"{window_sessions} stored trading sessions (actual bars used: {available})",
        window_sessions=window_sessions,
        available_sessions=available,
        data_sufficient=sufficient,
        as_of=as_of,
        basis=basis,
    )


def levels_to_dict(levels: Levels) -> dict:
    """JSON-friendly shape for API reports (NULL stays NULL — never 0)."""
    return {
        "support": levels.support,
        "resistance": levels.resistance,
        "method": levels.method,
        "window_sessions": levels.window_sessions,
        "available_sessions": levels.available_sessions,
        "data_sufficient": levels.data_sufficient,
        "as_of": levels.as_of.isoformat() if levels.as_of else None,
        "basis": levels.basis,
    }
