"""Market-data provider chain: owner-selected primary, optional fallback (Phase 14).

Ordering rule (documented, deterministic):

1. **Primary** — ``settings.market_data_provider``. ``"twelvedata"`` (or unset,
   which is the Phase-1 owner selection) builds a TwelveDataProvider;
   ``"yfinance"`` builds the fallback as the sole provider.
2. **Fallback** — the keyless yfinance provider is appended when
   ``settings.market_data_fallback == "yfinance"`` (the default) and the
   primary is not already yfinance.

Fallback triggers:
- the primary **raises** a provider error (404 plan-gate, 429 rate limit,
  5xx, transport fault after bounded retries), or
- the primary **returns zero bars** for the window.

Honesty:
- The provider that actually produced the rows reports its own
  ``provider_name``; rows are persisted under it, so per-row source
  attribution is preserved (market_prices.provider).
- The LAST provider returning an empty result is an honest "no bars in
  window" outcome, not an error (e.g. a market holiday on both sources).
- If every provider raises, the FIRST provider's error is re-raised so the
  worker's retry/backoff policy applies to the owner-selected primary.
"""

from __future__ import annotations

from typing import Optional

from app.collectors.exceptions import (
    ProviderError,
    ProviderUnavailableError,
)
from app.collectors.provider import MarketDataProvider, PriceRow
from app.collectors.twelve_data import TwelveDataProvider
from app.collectors.yfinance_data import YfinanceDataProvider
from app.core import config as config_mod
from app.core.logging import get_logger

_log = get_logger("collectors.chain")


def market_provider_chain(
    settings: config_mod.Settings,
    ticker: str,
    start,
    end,
    *,
    exchange: Optional[str] = None,
) -> list[MarketDataProvider]:
    """Build the ordered provider chain for one market-data collection."""
    primary_name = (getattr(settings, "market_data_provider", "") or "").strip().lower()
    if not primary_name:
        primary_name = "twelvedata"  # Phase 1 owner selection
    fallback_enabled = (
        getattr(settings, "market_data_fallback", "") or ""
    ).strip().lower() == "yfinance"

    def build(name: str) -> MarketDataProvider:
        if name == "yfinance":
            return YfinanceDataProvider(ticker, start, end, exchange=exchange, settings=settings)
        return TwelveDataProvider(ticker, start, end, exchange=exchange, settings=settings)

    chain = [build(primary_name)]
    if fallback_enabled and primary_name != "yfinance":
        chain.append(build("yfinance"))
    return chain


def fetch_daily_prices(
    chain: list[MarketDataProvider],
) -> tuple[MarketDataProvider, list[PriceRow], list[dict]]:
    """Run the chain in order.

    Returns ``(provider, rows, attempts)`` where ``attempts`` records, per
    provider in order, ``{"provider", "ok", "rows"|"error"}`` — safe to log
    (categories only, never raw provider payloads).
    """
    attempts: list[dict] = []
    first_error: Optional[ProviderError] = None

    for i, provider in enumerate(chain):
        try:
            rows = provider.get_daily_prices()
        except ProviderError as e:
            attempts.append({"provider": provider.provider_name, "ok": False, "error": e.category})
            if first_error is None:
                first_error = e
            _log.warning(
                "provider failed, falling through",
                extra={"provider": provider.provider_name, "category": e.category},
            )
            continue

        attempts.append({"provider": provider.provider_name, "ok": True, "rows": len(rows)})
        if rows:
            return provider, rows, attempts
        if i == len(chain) - 1:
            # Honest empty from the last provider: no bars in this window.
            return provider, [], attempts

    # Every provider raised.
    if first_error is not None:
        raise first_error
    raise ProviderUnavailableError("no market-data providers in the chain")
