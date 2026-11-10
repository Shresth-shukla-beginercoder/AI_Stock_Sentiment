"""Calendar chunking for the historical market-price backfill (Phase A1).

Why chunk: the provider cap (``provider_batch_limit``, default 120) limits the
number of bars a single call returns, and the yfinance fallback keeps only the
*last* ``provider_batch_limit`` bars. A single 6-month request (~125-180
trading days) would therefore be silently truncated to its most recent ~120
bars. The backfill splits the window into consecutive calendar chunks whose
*trading-day* count stays well under that cap, so every chunk fits in one
provider call and no historical bars are dropped.

Trading days are approximated as Mon-Fri. Exchange holidays are a *subset* of
those days, so a provider returns *at most* this many bars for a chunk (often
fewer) — a closed day is an honest gap, never fabricated.
"""

from __future__ import annotations

from datetime import date, timedelta


def trading_days_between(start: date, end: date) -> list[date]:
    """Mon-Fri calendar days in the inclusive range [start, end].

    A Mon-Fri *approximation* that ignores exchange holidays, so the count is
    an upper bound on the bars a provider will return for the window.
    Returns [] when ``start > end``.
    """
    if start > end:
        return []
    days: list[date] = []
    d = start
    while d <= end:
        if d.weekday() < 5:  # Monday=0 .. Friday=4
            days.append(d)
        d += timedelta(days=1)
    return days


def iter_chunk_windows(
    start: date,
    end: date,
    max_trading_days: int,
) -> list[tuple[date, date]]:
    """Split the inclusive range [start, end] into consecutive calendar windows.

    Each window spans from the first to the last trading day of a run of at most
    ``max_trading_days`` trading days, so a provider returns <= that many bars
    for a chunk (well under the 120-bar cap). Chunks are contiguous and
    preserve every trading day: the first chunk begins at the first trading day
    on/after ``start`` and the last ends at the last trading day on/before
    ``end``. Returns [] when the window contains no trading days.

    Raises ``ValueError`` if ``max_trading_days < 1`` or ``start > end``.
    """
    if max_trading_days < 1:
        raise ValueError("max_trading_days must be >= 1")
    if start > end:
        raise ValueError("start must be <= end")

    tdays = trading_days_between(start, end)
    chunks: list[tuple[date, date]] = []
    for i in range(0, len(tdays), max_trading_days):
        run = tdays[i : i + max_trading_days]
        chunks.append((run[0], run[-1]))
    return chunks
