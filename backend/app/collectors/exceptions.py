"""Provider error taxonomy.

Collectors raise these (or a subclass of :class:`ProviderError`) so the retry
wrapper in ``collectors/retry.py`` and the CLI/worker can classify outcomes
honestly. ``category`` is a stable, lowercase string that may appear in logs
(it never carries a secret or a raw provider payload).
"""

from __future__ import annotations


class ProviderError(Exception):
    """Base class for all collector/provider failures."""

    #: short stable tag, safe to log (never a secret / raw body).
    category: str = "provider_error"

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        #: HTTP status if the error came from a transport response, else None.
        self.status = status


class AuthError(ProviderError):
    """Credential missing/invalid, or the provider rejected the key (401/403)."""

    category = "auth"


class RateLimitError(ProviderError):
    """Rate-limited / quota exhausted (typically 429). Retryable, back off."""

    category = "rate_limit"


class TransientError(ProviderError):
    """Transient transport fault (5xx, timeout, connection reset). Retryable."""

    category = "transient"


class InvalidResponseError(ProviderError):
    """Provider answered but the payload failed schema/numeric validation.

    Not retryable — re-fetching the same symbol won't fix a malformed body.
    """

    category = "invalid_response"


class SymbolNotFoundError(ProviderError):
    """The provider has no data for the requested symbol (404 / empty)."""

    category = "symbol_not_found"


class ProviderUnavailableError(ProviderError):
    """Provider endpoint unreachable or down in a way that is not a clean 4xx/5xx.

    Distinct from TransientError: marks 'we could not reach the provider at all'.
    """

    category = "unavailable"
