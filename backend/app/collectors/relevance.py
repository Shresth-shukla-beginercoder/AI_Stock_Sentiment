"""Asset-relevance gating for news items (W3).

Exa returns *candidate* articles for a ticker query. Some are genuinely
about the asset; some are unrelated (the search is semantic, not exact).
Attributing an unrelated article to an asset pollutes its sentiment and
report. This module decides per item, from the item's own text only:

- ``relevant``    — the asset's name or ticker is present (drop-risk: none).
- ``ambiguous``   — a weak signal only (e.g. the ticker appears embedded in a
                    longer digit run, or only one word of a multi-word name
                    matched). The item is *kept* (never invented away) but
                    flagged, so a reviewer can see why it survived.
- ``irrelevant``  — no name and no ticker mention anywhere in title/body:
                    the item is *dropped* and counted, never persisted under
                    the asset.
- ``no_ticker``   — caller supplied no identifiers at all: nothing can be
                    judged, so every item is kept unfiltered (honest).

The filter never edits titles, bodies, URLs, dates or source metadata —
it only decides keep/drop and flags.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from app.collectors.exa import NewsItem
from app.core.logging import get_logger

_log = get_logger("collectors.relevance")


@dataclass
class RelevanceCounts:
    """Outcome of filtering one batch against one asset."""

    relevant: int = 0
    ambiguous: int = 0
    irrelevant_dropped: int = 0
    no_ticker_kept: int = 0
    total_in: int = 0


def _has_name(text_lower: str, name: Optional[str]) -> tuple[bool, bool]:
    """Return (full_match, partial_match) of the company name in the text."""
    if not name or len(name.strip()) < 3:
        return False, False
    phrase = name.strip().lower()
    if phrase in text_lower:
        return True, True
    # Multi-word names: any single word of 4+ chars matching is a weak signal.
    words = [w for w in re.findall(r"[a-z]+", phrase) if len(w) >= 4]
    partial = any(re.search(rf"\b{re.escape(w)}\b", text_lower) for w in words)
    return False, partial


def _ticker_hits(text_lower: str, ticker: Optional[str],
                 provider_ticker: Optional[str]) -> tuple[bool, bool]:
    """Return (exact_hit, embedded_hit).

    exact_hit:    the ticker appears as a standalone token (``0700`` not
                  inside ``407005``; letters use plain word boundaries).
    embedded_hit: the ticker appears only as part of a longer digit run — a
                  weak, ambiguous signal.
    """
    exact = False
    embedded = False
    if provider_ticker:
        exact = provider_ticker.lower() in text_lower
    if ticker:
        t = ticker.strip().lower()
        if t.isdigit():
            if re.search(rf"(?<!\d){re.escape(t)}(?!\d)", text_lower):
                exact = True
            elif re.search(re.escape(t), text_lower):
                embedded = True  # digits present but only inside a longer run
        else:
            if re.search(rf"\b{re.escape(t)}\b", text_lower):
                exact = True
    return exact, embedded


def filter_asset_relevant(
    items: list[NewsItem],
    *,
    name: Optional[str] = None,
    ticker: Optional[str] = None,
    provider_ticker: Optional[str] = None,
) -> tuple[list[NewsItem], RelevanceCounts]:
    """Keep items that mention the asset; drop clearly-unrelated ones.

    Returns (kept_items, counts). Every kept item keeps all of its original
    metadata (title/body/URL/date/source) untouched.
    """
    counts = RelevanceCounts(total_in=len(items))

    if not name and not ticker and not provider_ticker:
        _log.info("relevance filter: no identifiers supplied — keeping all items unfiltered",
                  extra={"kept": len(items)})
        counts.no_ticker_kept = len(items)
        return list(items), counts

    kept: list[NewsItem] = []
    for item in items:
        text = f"{item.title or ''}\n{item.body or ''}".lower()
        full, partial = _has_name(text, name)
        exact, embedded = _ticker_hits(text, ticker, provider_ticker)

        if full or exact:
            counts.relevant += 1
            kept.append(item)
        elif partial or embedded:
            counts.ambiguous += 1
            kept.append(item)  # kept, flagged by counts
            _log.info("relevance: ambiguous item kept",
                      extra={"title": (item.title or "")[:80]})
        else:
            counts.irrelevant_dropped += 1
            _log.info("relevance: irrelevant item dropped",
                      extra={"title": (item.title or "")[:80],
                             "url": item.url})

    _log.info("relevance filter complete",
              extra={"relevant": counts.relevant, "ambiguous": counts.ambiguous,
                     "dropped": counts.irrelevant_dropped})
    return kept, counts


__all__ = ["filter_asset_relevant", "RelevanceCounts"]
