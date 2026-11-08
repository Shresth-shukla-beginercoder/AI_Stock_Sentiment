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
    # Apify credential. APIFY_API_TOKEN is the canonical name (Phase 5 spec);
    # APIFY_API_KEY is a Phase-1 legacy alias kept so an existing local .env
    # keeps working until renamed. apify_token() prefers the token.
    apify_api_token: SecretStr | None = None
    apify_api_key: SecretStr | None = None

    # --- Market data provider: owner-selected as "twelve_data" (capability UNVERIFIED).
    # --- The name is a config value; vendor symbol coverage/quota/ToS stay UNVERIFIED
    # until a real Phase 5 fetch. A configured key does NOT mean the provider works.
    market_data_provider: str = ""  # e.g. "twelve_data" when .env sets it
    twelve_data_api_key: SecretStr | None = None

    # --- Provider collection operations (Phase 5) ---
    # Bounded timeouts / retries / batch size and the news+social lookback window.
    provider_timeout_seconds: float = 30.0
    provider_max_retries: int = 3
    provider_retry_base_delay_seconds: float = 0.5
    provider_retry_backoff_factor: float = 2.0
    provider_retry_max_delay_seconds: float = 30.0
    provider_batch_limit: int = 120  # max bars / results fetched per call
    collection_window_days: int = 10  # lookback for news / social (CLAUDE.md)

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
        "apify_api_key",
        "twelve_data_api_key",
    )

    def apify_token(self) -> str | None:
        """Effective Apify credential: APIFY_API_TOKEN, else legacy APIFY_API_KEY."""
        if self.apify_api_token:
            return self.apify_api_token.get_secret_value()
        if self.apify_api_key:
            return self.apify_api_key.get_secret_value()
        return None

    def missing_credentials(self) -> list[str]:
        """Names (upper-cased env var form) of credentials that are unset."""
        return [f.upper() for f in self.CREDENTIAL_FIELDS if not getattr(self, f)]

    def configured_credentials(self) -> list[str]:
        """Names (upper-cased env var form) of credentials that are set."""
        return [f.upper() for f in self.CREDENTIAL_FIELDS if getattr(self, f)]


@lru_cache
def get_settings() -> Settings:
    return Settings()
