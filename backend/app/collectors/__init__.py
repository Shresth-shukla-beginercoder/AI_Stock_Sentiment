# collectors: provider clients + normalisation (Phase 5).
#
#   provider.py     - abstract MarketDataProvider interface + PriceRow
#   exceptions.py   - provider error taxonomy (safe-to-log categories)
#   retry.py        - bounded exponential-backoff retry (tenacity)
#   normalize.py    - pure normalisation services (symbols, URLs, hashes, text)
#   twelve_data.py  - Twelve Data daily OHLCV (concrete MarketDataProvider)
#   yfinance_data.py- Yahoo Finance daily OHLCV (keyless fallback, Phase 14)
#   chain.py        - primary->fallback provider chain (Phase 14)
#   exa.py          - Exa financial-news collector
#   apify.py        - Apify social-discussion collector + Actor verification

from app.collectors.provider import MarketDataProvider, PriceRow
from app.collectors.exceptions import (
    ProviderError,
    AuthError,
    RateLimitError,
    TransientError,
    InvalidResponseError,
    SymbolNotFoundError,
    ProviderUnavailableError,
)
from app.collectors.twelve_data import TwelveDataProvider
from app.collectors.yfinance_data import YfinanceDataProvider
from app.collectors.chain import market_provider_chain, fetch_daily_prices
from app.collectors.exa import ExaNewsCollector, NewsItem
from app.collectors.apify import (
    ApifySocialCollector,
    ActorAvailability,
    CandidateActor,
    SocialPostItem,
    CANDIDATE_ACTORS,
)

__all__ = [
    "MarketDataProvider", "PriceRow",
    "ProviderError", "AuthError", "RateLimitError", "TransientError",
    "InvalidResponseError", "SymbolNotFoundError", "ProviderUnavailableError",
    "TwelveDataProvider",
    "YfinanceDataProvider",
    "market_provider_chain", "fetch_daily_prices",
    "ExaNewsCollector", "NewsItem",
    "ApifySocialCollector", "ActorAvailability", "CandidateActor",
    "SocialPostItem", "CANDIDATE_ACTORS",
]
