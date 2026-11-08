"""Bounded retry with exponential backoff for provider calls.

Uses ``tenacity`` so every provider shares one bounded, well-understood
policy. Only the retryable provider error classes (and httpx transport errors)
are retried; authentication / invalid-response / missing-symbol errors are
raised immediately — re-fetching them cannot succeed.

Rate-limit responses may set ``retry_after`` seconds on the raised
:class:`~app.collectors.exceptions.RateLimitError`; the wait honours that but
is still capped so a hostile/buggy header can't hang the collector.
"""

from __future__ import annotations

import httpx
from tenacity import (
    Retrying,
    retry_if_exception_type,
    before_sleep_log,
    stop_after_attempt,
)
import logging

from app.collectors.exceptions import (
    ProviderError,
    RateLimitError,
    TransientError,
    ProviderUnavailableError,
)
from app.core import config as config_mod
from app.core.logging import get_logger

_log = get_logger("collectors.retry")

#: Exceptions worth retrying. Everything else is re-raised on the first failure.
RETRYABLE = (
    TransientError,
    RateLimitError,
    ProviderUnavailableError,
    httpx.TransportError,  # timeouts, connection resets
)


class _HonourRetryAfter:
    """Wait strategy: exponential backoff, but respect a RateLimit retry-after.

    Bounded to ``max_delay`` so a bad header cannot stall the collector.
    """

    def __init__(self, base: float, backoff: float, max_delay: float) -> None:
        self._base = base
        self._backoff = backoff
        self._max_delay = max_delay

    def __call__(self, retry_state) -> float:
        attempt = retry_state.attempt_number  # 1-based
        exponential = min(self._base * (self._backoff ** (attempt - 1)), self._max_delay)
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        hint = getattr(exc, "retry_after", None)
        if hint is not None:
            try:
                hinted = min(float(hint) + 0.25, self._max_delay)
                return max(exponential, hinted)
            except (TypeError, ValueError):
                return exponential
        return exponential


def _is_rate_limited(error: ProviderError) -> bool:
    return isinstance(error, RateLimitError)


def bounded_retry(
    func,
    *,
    settings: config_mod.Settings | None = None,
) -> object:
    """Run ``func`` under a bounded exponential-backoff retry.

    ``func`` must accept no arguments (build it with a closure / functools).
    Returns the successful result, or re-raises the last ProviderError /
    transport error once retries are exhausted.
    """
    s = settings or config_mod.get_settings()
    attempts = max(1, s.provider_max_retries + 1)
    wait = _HonourRetryAfter(
        s.provider_retry_base_delay_seconds,
        s.provider_retry_backoff_factor,
        s.provider_retry_max_delay_seconds,
    )

    def wait_with_log(retry_state) -> float:
        base_wait = wait(retry_state)
        if base_wait > 0:
            _log.debug(
                "retrying provider call",
                extra={
                    "provider": getattr(retry_state.args[0] if retry_state.args else None, "provider_name", "provider"),
                    "attempt": retry_state.attempt_number,
                    "wait_seconds": round(base_wait, 3),
                    "error_category": getattr(retry_state.outcome.exception(), "category", None),
                },
            )
        return base_wait

    retrying = Retrying(
        retry=retry_if_exception_type(RETRYABLE),
        stop=stop_after_attempt(attempts),
        wait=wait_with_log,
        reraise=True,
    )
    return retrying(func)
