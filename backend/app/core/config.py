"""Application settings.

Rules (see CLAUDE.md):
- Real environment variables always beat .env values (pydantic-settings default).
- Secrets use SecretStr; nothing secret ever enters logs, responses or images.
- DATA_MODE is an explicit configuration setting with a safe default ("demo").
  It is NEVER inferred from credential presence.
- missing_credentials() returns credential field NAMES only.
"""

from functools import lru_cache
from typing import Literal
from urllib.parse import quote

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- PostgreSQL ---
    postgres_host: str = "localhost"
    postgres_port: int = 5437  # dev default: host-published port (5437:5432)
    postgres_user: str = "stock"
    postgres_password: SecretStr = SecretStr("stock_dev_password")
    postgres_db: str = "stock_sentiment"
    database_url: str | None = None  # optional full-URL override

    # --- Data mode: explicit, safe default "demo" ---
    data_mode: Literal["live", "demo"] = "demo"

    # --- CORS: explicit origin list, never "*" ---
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # --- Credentials (SecretStr; presence is reported, never their values) ---
    api_admin_key: SecretStr | None = None
    exa_api_key: SecretStr | None = None
    tavily_api_key: SecretStr | None = None
    # Apify credential. APIFY_API_TOKEN is the single canonical name (used in
    # Render and the local .env). apify_token() returns it, falling back to the
    # legacy APIFY_API_KEY alias when only that is set (compose exposes both;
    # the canonical name wins).
    apify_api_token: SecretStr | None = None
    apify_api_key: SecretStr | None = None  # legacy alias, never the primary

    # --- Market data provider: owner-selected as "twelve_data" (capability UNVERIFIED).
    # --- The name is a config value; vendor symbol coverage/quota/ToS stay UNVERIFIED
    # until a real Phase 5 fetch. A configured key does NOT mean the provider works.
    market_data_provider: str = ""  # e.g. "twelve_data" when .env sets it
    twelve_data_api_key: SecretStr | None = None

    # --- Phase 14: market-data fallback + Apify actor refs + ML determinism ---
    # Keyless secondary provider appended behind the primary when the primary
    # errors or returns no bars. "yfinance" by default so plan-gated HKEX /
    # rate-limited KRX symbols stay retrievable. Vendor capability/ToS remain
    # UNVERIFIED until a live fetch; bars fetched this way are stored under
    # provider="yfinance" (per-row attribution). "" disables the fallback.
    market_data_fallback: str = "yfinance"

    # Apify actor refs per social platform (owner-supplied; UNVERIFIED until a
    # real verify/run). Empty ref = not configured: the collector records that
    # honestly and never invents an Actor id. The two HK defaults are the
    # Phase 5 candidates.
    apify_actor_lihkg: str = "claude_code_reviewer/lihkg-scraper-en"
    apify_actor_telegram: str = "lofomachines/telegram-keyword-search-scraper"
    apify_actor_kakao: str = ""
    apify_actor_naver: str = ""

    # W1: bounded, cost-capped Actor execution. A collect:social job runs an
    # actor only when it was verified for this exchange's configured refs and
    # its input can be built from the actor's OWN schema/example (never guessed).
    # The caps keep any run small and cheap.
    apify_run_wait_seconds: int = 120       # poll deadline for one Actor run
    apify_run_max_items: int = 30          # dataset items read per run (smoke size)
    apify_run_max_charge_usd: float = 1.0  # hard per-run charge cap (USD)

    # ML determinism + out-of-sample rigor (Phase 14): fixed random seed and a
    # strict chronological holdout period after the walk-forward CV.
    ml_random_seed: int = 42
    ml_holdout_ratio: float = 0.2

    # --- Provider collection operations (Phase 5) ---
    # Bounded timeouts / retries / batch size and the news+social lookback window.
    provider_timeout_seconds: float = 30.0
    provider_max_retries: int = 3
    provider_retry_base_delay_seconds: float = 0.5
    provider_retry_backoff_factor: float = 2.0
    provider_retry_max_delay_seconds: float = 30.0
    provider_batch_limit: int = 120  # max bars / results fetched per call
    collection_window_days: int = 10  # lookback for news / social (CLAUDE.md)

    # --- Historical market-price backfill (Phase A1) ---
    # The backfill splits the lookback into calendar chunks whose trading-day
    # count stays under the provider's per-call bar cap (provider_batch_limit,
    # default 120) so no chunk is silently truncated to its most recent bars.
    # Both knobs are defaults only; real overrides come from the CLI flags.
    backfill_chunk_trading_days: int = 60   # max trading days per backfill chunk
    backfill_default_days: int = 183        # ~6 months of calendar lookback

    # --- Sentiment engine (Phase 6) ---
    sentiment_social_weight: float = 0.4  # CLAUDE.md: social weight in combined score
    sentiment_news_weight: float = 0.6    # CLAUDE.md: news weight in combined score
    sentiment_threshold_bullish: float = 0.15   # score > 0.15 → bullish signal
    sentiment_threshold_bearish: float = -0.15  # score < -0.15 → bearish signal
    sentiment_min_items: int = 5  # min posts+news for sufficient data
    sentiment_window_days: int = 10  # rolling window for aggregation

    # --- Support / resistance (W4) ---
    # Trading sessions of stored price bars used for the window-extremes levels.
    support_resistance_window_sessions: int = 20
    hf_cache_dir: str = "/models"  # Hugging Face model cache (hf_models volume)

    # ------------------------------------------------------------------ utils
    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def database_url_resolved(self) -> str:
        """Build the URL from parts; DATABASE_URL is the optional full override."""
        if self.database_url:
            return self.database_url
        user = quote(self.postgres_user, safe="")
        password = quote(self.postgres_password.get_secret_value(), safe="")
        return (
            f"postgresql+psycopg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    CREDENTIAL_FIELDS: tuple[str, ...] = (
        "api_admin_key",
        "exa_api_key",
        "tavily_api_key",
        "apify_api_token",
        "twelve_data_api_key",
    )

    def apify_token(self) -> str | None:
        """Effective Apify credential.

        APIFY_API_TOKEN (canonical) wins; the legacy APIFY_API_KEY alias is used
        only when the canonical name is unset.
        """
        if self.apify_api_token:
            return self.apify_api_token.get_secret_value()
        if self.apify_api_key:
            return self.apify_api_key.get_secret_value()
        return None

    def _apify_present(self) -> bool:
        return bool(self.apify_token())

    def missing_credentials(self) -> list[str]:
        """Names (upper-cased env var form) of credentials that are unset.

        Apify is satisfied by APIFY_API_TOKEN or the legacy APIFY_API_KEY
        alias; it is reported missing only when neither is set.
        """
        missing = []
        for f in self.CREDENTIAL_FIELDS:
            if f == "apify_api_token":
                if not self._apify_present():
                    missing.append("APIFY_API_TOKEN")
            elif not getattr(self, f):
                missing.append(f.upper())
        return missing

    def configured_credentials(self) -> list[str]:
        """Names (upper-cased env var form) of credentials that are set."""
        configured = []
        for f in self.CREDENTIAL_FIELDS:
            if f == "apify_api_token":
                if self._apify_present():
                    configured.append("APIFY_API_TOKEN")
            elif getattr(self, f):
                configured.append(f.upper())
        return configured



@lru_cache
def get_settings() -> Settings:
    return Settings()
