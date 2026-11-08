"""Abstract market-data provider interface.

Phase 1 boundary: this is interface-only. No vendor implementation, no live
data ingestion. The concrete provider is selected only after the user approves
one from docs/PROVIDER_COVERAGE.md.

Design goal (see master prompt): price collection sits behind
``get_daily_prices(ticker, start, end)`` so vendors are swappable without
touching the rest of the system.

All dates/times are UTC. Naive timestamps are rejected at the boundary in
Phase 5 (``to_utc``); this interface documents the contract only.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Optional


@dataclass(frozen=True)
class PriceRow:
    """A single daily OHLCV bar, aligned to the provider's trading calendar.

    Fields that are unknown are None (never 0). ``trade_date`` is a timezone-
    aware UTC datetime representing the session close. ``close`` is required
    (a bar without a close is malformed); open/high/low/volume may be None.
    """

    ticker: str
    trade_date: datetime  # UTC, aware
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: float
    volume: Optional[int] = None  # None = unknown

    def __post_init__(self) -> None:
        # Contract guard: reject naive timestamps at the interface.
        if self.trade_date.tzinfo is None:
            raise ValueError(
                f"PriceRow.trade_date must be tz-aware UTC, got {self.trade_date!r}"
            )
        if self.trade_date.tzinfo is not None and self.trade_date.utcoffset() != timezone.utc.utcoffset(None):
            # Accept aware non-UTC by normalising; reject only naive per the data rule.
            object.__setattr__(self, "trade_date", self.trade_date.astimezone(timezone.utc))


class MarketDataProvider(abc.ABC):
    """Swappable market-data vendor behind a single method.

    Implementations must be deterministic about their source attribution so the
    schema's ``provider`` column can record which vendor produced a row.
    """

    #: Stable, human-readable vendor name stored on market_prices.provider.
    provider_name: str = "abstract"

    def __init__(self, ticker: str, start: date, end: date) -> None:
        self.ticker = ticker
        self.start = start
        self.end = end

    @abc.abstractmethod
    def get_daily_prices(self) -> list[PriceRow]:
        """Return daily OHLCV bars for ``self.ticker`` in [start, end].

        Must only use data available up to the requested window; no look-ahead.
        """
        raise NotImplementedError


def _utc_datetime(d: date, hour: int = 16, minute: int = 0) -> datetime:
    """Helper for constructing aware UTC datetimes from a date.

    NOTE: the exchange-specific close-time/session logic belongs in
    ``app/features`` (Phase 8). This helper is only for interface examples/tests.
    """
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc)
