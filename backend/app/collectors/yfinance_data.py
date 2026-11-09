"""Yahoo Finance — secondary (fallback) market-data provider (Phase 14).

Free, keyless secondary source, used behind the owner-selected primary
provider (Twelve Data) when the primary cannot serve a symbol: HKEX is
plan-gated (404) and KRX resolution is rate-limited (429) on the current
plan (docs/PROVIDER_COVERAGE.md). Selected as fallback option #1 there.

Truth Rules:
- Vendor capability / symbol coverage / ToS stay **UNVERIFIED** until a real
  fetch confirms them. A configured import does not mean the provider works.
- Every bar fetched through this provider is persisted under
  ``provider="yfinance"`` so the schema keeps per-row source attribution.

``fetch`` is injectable so tests exercise the DataFrame → PriceRow mapping
without any network. Live mode lazily imports ``yfinance`` so importing this
module works in environments without the dependency installed.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Callable, Optional

import pandas as pd

from app.collectors.exceptions import (
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
    SymbolNotFoundError,
    TransientError,
)
from app.collectors.normalize import normalize_symbol, ohlv_to_price_row
from app.collectors.provider import MarketDataProvider, PriceRow
from app.core import config as config_mod
from app.core.logging import get_logger

_log = get_logger("collectors.yfinance")

#: (symbol, start_iso, end_exclusive_iso) -> OHLCV DataFrame, daily index.
FetchFn = Callable[[str, str, str], "pd.DataFrame"]


def _cell(rec, col: str) -> Optional[float]:
    """Numeric cell -> float; NaN / missing -> None (never 0)."""
    try:
        value = rec[col]
    except (KeyError, IndexError, TypeError):
        return None
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass  # non-numeric sentinel; let the float() below decide
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class YfinanceDataProvider(MarketDataProvider):
    """Daily OHLCV from Yahoo Finance (``yfinance`` library).

    - Symbol is normalised with the shared service: HKEX ``0700`` ->
      ``0700.HK``, KRX ``005930`` -> ``005930.KS`` (vendor conventions the
      library already uses for these exchanges).
    - ``history`` is called with ``auto_adjust=False`` so stored prices are the
      raw exchange prints (documented choice; splits handled by Yahoo's raw
      split-adjusted series, dividers NOT applied).
    - The daily frame's index is exchange-local session dates; we reduce each
      bar to its session date (same convention as the Twelve Data adapter:
      the exchange trading day, stored as a UTC calendar date).
    - A bar without a close is skipped (partial current-day bars happen),
      counted and logged — never fabricated.
    - Empty frame => honestly empty result (no bars in the window).
    """

    provider_name = "yfinance"

    def __init__(
        self,
        ticker: str,
        start: object,
        end: object,
        *,
        exchange: Optional[str] = None,
        settings: Optional[config_mod.Settings] = None,
        fetch: Optional[FetchFn] = None,
    ) -> None:
        super().__init__(ticker, start, end)
        self.exchange = exchange
        self._settings = settings or config_mod.get_settings()
        self._fetch = fetch

    # -- live fetch ----------------------------------------------------------
    def _live_fetch(self, symbol: str) -> "pd.DataFrame":
        import yfinance  # lazy: only the live path needs the dependency

        # Yahoo treats ``end`` as exclusive; extend by one day to include
        # the requested final session.
        end_iso = (self.end + timedelta(days=1)).isoformat()
        try:
            df = yfinance.Ticker(symbol).history(
                start=self.start.isoformat(),
                end=end_iso,
                interval="1d",
                auto_adjust=False,
            )
        except Exception as e:  # the underlying HTTP client raises requests errors
            text = str(e)
            if "429" in text:
                raise RateLimitError("Yahoo Finance rate limit (HTTP 429)") from e
            raise TransientError(f"Yahoo Finance fetch failed: {e}") from e
        return df

    # -- public contract -----------------------------------------------------
    def get_daily_prices(self) -> list[PriceRow]:
        symbol = normalize_symbol(self.ticker, self.exchange)
        if not symbol:
            raise SymbolNotFoundError("cannot derive a symbol", status=None)

        end_iso = (self.end + timedelta(days=1)).isoformat()
        if self._fetch is not None:
            df = self._fetch(symbol, self.start.isoformat(), end_iso)
        else:
            df = self._live_fetch(symbol)

        if df is None or len(df) == 0:
            _log.info(
                "yfinance: no bars in window",
                extra={"ticker": self.ticker, "symbol": symbol, "exchange": self.exchange},
            )
            return []

        rows: list[PriceRow] = []
        skipped = 0
        for idx, rec in df.iterrows():
            close = _cell(rec, "Close")
            if close is None:
                # Partial / malformed bar (e.g. an in-progress session): skip
                # honestly rather than fabricate a close price.
                skipped += 1
                continue
            volume = _cell(rec, "Volume")
            try:
                rows.append(
                    ohlv_to_price_row(
                        self.ticker,
                        idx,  # session date (Timestamp or date)
                        _cell(rec, "Open"),
                        _cell(rec, "High"),
                        _cell(rec, "Low"),
                        close,
                        int(volume) if volume is not None else None,
                    )
                )
            except ProviderError:
                skipped += 1
                continue

        if skipped:
            _log.warning(
                "yfinance: bars without a usable close skipped",
                extra={"symbol": symbol, "skipped": skipped, "kept": len(rows)},
            )

        rows.sort(key=lambda r: r.trade_date)
        cap = self._settings.provider_batch_limit
        if len(rows) > cap:
            rows = rows[-cap:]
        _log.info(
            "yfinance fetch",
            extra={"ticker": self.ticker, "symbol": symbol, "exchange": self.exchange, "rows": len(rows)},
        )
        return rows
