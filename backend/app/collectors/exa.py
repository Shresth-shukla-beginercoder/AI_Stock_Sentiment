"""Exa — financial-news collector (Phase 5).

Uses the official ``exa_py`` SDK. The client is injectable so tests can stub the
search without any network. Captures title / URL / publication date / source
domain / body text; never invents article text, headlines, URLs, dates or
authors — anything the provider does not return is left ``None``.

``NewsItem`` is the normalized candidate; persistence assigns ``asset_id`` and
the ``url_hash`` dedupe key.
"""

from __future__ import annotations

import dataclasses
import re
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlsplit

import exa_py

from app.collectors.exceptions import (
    ProviderError,
    AuthError,
    InvalidResponseError,
    TransientError,
)
from app.collectors.normalize import clean_text, parse_timestamp, url_hash, sha256_hex
from app.collectors.retry import bounded_retry
from app.core import config as config_mod
from app.core.logging import get_logger

_log = get_logger("collectors.exa")


@dataclasses.dataclass
class NewsItem:
    """A normalized news article candidate (pre-persistence)."""

    url: Optional[str]
    url_hash: Optional[str]
    title: Optional[str]
    body: Optional[str]
    published_at: Optional[datetime]
    author: Optional[str]
    source: Optional[str]  # source domain, or "exa" when absent
    external_id: Optional[str] = None
    content_hash: Optional[str] = None
    is_demo: bool = False

    def normalized(self) -> "NewsItem":
        """Re-run text/URL normalization defensively; idempotent."""
        self.body = clean_text(self.body) if self.body is not None else None
        self.title = clean_text(self.title) if self.title is not None else None
        if self.url is not None and not self.url_hash:
            self.url_hash = url_hash(self.url)
        return self


_DOMAIN_RE = re.compile(r"https?://([^\s/?#]+)", re.I)


def _domain_of(url: Optional[str]) -> Optional[str]:
    if url:
        netloc = urlsplit(url).netloc.lower()
        if netloc:
            return netloc
        m = _DOMAIN_RE.search(url)
        if m:
            return m.group(1).lower()
    return None


class ExaNewsCollector:
    """Search financial news for an asset over a bounded window."""

    provider_name = "exa"

    def __init__(
        self,
        *,
        settings: Optional[config_mod.Settings] = None,
        api_key: Optional[str] = None,
        exa: Optional[exa_py.Exa] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self._settings = settings or config_mod.get_settings()
        self._injected = exa
        key = api_key
        if key is None:
            k = self._settings.exa_api_key
            key = k.get_secret_value() if k else None
        self._api_key = key
        self._timeout = timeout or self._settings.provider_timeout_seconds

    def _client(self) -> exa_py.Exa:
        if self._injected is not None:
            return self._injected
        if not self._api_key:
            raise AuthError("EXA_API_KEY is not configured")
        return exa_py.Exa(api_key=self._api_key, timeout=self._timeout)

    @staticmethod
    def _window(days: int, end: Optional[date]) -> tuple[str, str]:
        """Return (start_date, end_date) as YYYY-MM-DD for the lookback window."""
        anchor = end or datetime.now(timezone.utc).date()
        start = anchor - timedelta(days=days)
        return start.isoformat(), anchor.isoformat()

    def search(
        self,
        query: str,
        *,
        days: Optional[int] = None,
        end: Optional[date] = None,
        num_results: Optional[int] = None,
        include_domains: Optional[list[str]] = None,
        company_name: Optional[str] = None,
    ) -> list[NewsItem]:
        """Run one news search and return normalized, deduped candidates."""
        if not query or not query.strip():
            raise InvalidResponseError("empty Exa query")
        window_days = days if days is not None else self._settings.collection_window_days
        start_d, end_d = self._window(window_days, end)
        n = num_results or min(self._settings.provider_batch_limit, 20)

        exa = self._client()

        def _do():
            try:
                contents = exa_py.ContentsOptions(text=True)
            except Exception:  # SDK version without ContentsOptions ctor
                contents = None
            return exa.search(
                query=query,
                num_results=n,
                include_domains=include_domains,
                start_published_date=start_d,
                end_published_date=end_d,
                contents=contents,
                category="news",
            )

        resp = bounded_retry(_do, settings=self._settings)

        results = getattr(resp, "results", None)
        if results is None:
            # Defensive: SDK version differences. An empty/absent result set is a
            # legitimate "no news" outcome, not an error.
            results = []

        seen: set[str] = set()
        items: list[NewsItem] = []
        for res in results:
            url = getattr(res, "url", None)
            if not url:
                continue  # no URL -> cannot dedupe/attribute; skip honestly
            uh = url_hash(url)
            if uh in seen:
                continue
            seen.add(uh)

            published = parse_timestamp(getattr(res, "published_date", None))
            text = getattr(res, "text", None) or getattr(res, "summary", None)
            item = NewsItem(
                url=url,
                url_hash=uh,
                title=getattr(res, "title", None),
                body=clean_text(text),
                published_at=published,
                author=getattr(res, "author", None),
                source=_domain_of(url),
                external_id=getattr(res, "id", None),
            )
            item.content_hash = sha256_hex(f"{item.title or ''}\n{item.body or ''}")
            items.append(item)

        _log.info(
            "exa news search",
            extra={
                "query": query[:120],
                "window_days": window_days,
                "results": len(items),
                "company": company_name,
            },
        )
        return items


def _wrap_provider_errors(func):
    """Map SDK/transport exceptions onto the provider error taxonomy."""
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except exa_py.ExaTimeoutError as e:
            raise TransientError(f"Exa request timed out: {e}") from e
        except AuthError:
            raise
        except Exception as e:
            msg = str(e).lower()
            if any(t in msg for t in ("401", "403", "unauthorized", "invalid api key", "invalid_api_key")):
                raise AuthError(f"Exa auth failure: {e}") from e
            if any(t in msg for t in ("429", "rate limit", "too many requests", "quota")):
                from app.collectors.exceptions import RateLimitError

                raise RateLimitError(f"Exa rate limit: {e}") from e
            if isinstance(e, (TransientError, InvalidResponseError, ProviderError)):
                raise
            raise TransientError(f"Exa request failed: {e}") from e

    return wrapper


# Wrap the public search method once, in place, so call sites stay unchanged.
ExaNewsCollector.search = _wrap_provider_errors(ExaNewsCollector.search)  # type: ignore[assignment]
