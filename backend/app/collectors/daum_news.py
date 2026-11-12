"""Daum news collector (KRX / Korea financial news).

Runs the ``ardent_fork~daum-news`` Actor (canonical ID
``Nb4IPtZTzc2RtuH7S``) via the Apify client, then maps its dataset output to
normalized :class:`NewsItem` rows. The fetch is bounded; missing fields stay
NULL. This is a NEWS source, handled by ``handle_collect_news`` (not the social
path).
"""
from __future__ import annotations

from typing import Optional

import apify_client

from app.collectors.exa import NewsItem
from app.collectors.normalize import clean_text, parse_timestamp, url_hash, sha256_hex
from app.core.config import get_settings
from app.core.logging import get_logger

_log = get_logger("collectors.daum_news")


class DaumNewsCollector:
    """Fetch + map Daum news articles. Standalone: not a social collector."""

    provider_name = "daum"

    def __init__(self, *, settings=None, token: Optional[str] = None) -> None:
        self._settings = settings or get_settings()
        self._token = token if token is not None else self._settings.apify_token()

    def _client(self) -> apify_client.ApifyClient:
        if not self._token:
            from app.collectors.exceptions import AuthError
            raise AuthError("Apify credential is not configured (APIFY_API_TOKEN)")
        return apify_client.ApifyClient(
            token=self._token,
            timeout_medium=self._settings.provider_timeout_seconds,
        )

    def fetch(self, sections: Optional[list[str]] = None,
              max_items: int = 20, wait: int = 120) -> list[dict]:
        """Run the Daum Actor and return its raw dataset items.

        Uses the canonical Actor ID (tilde refs 404 on POST /runs). The input
        fields are the Actor's OWN documented schema — never invented.
        """
        actor_id = self._settings.apify_actor_daum
        if not actor_id:
            raise ValueError("apify_actor_daum is not configured")

        run_input: dict = {
            "sections": sections or ["economy", "stock", "finance", "industry"],
            "maxItems": max_items,
            "fetchArticles": True,
        }
        _log.info("running daum news actor",
                  extra={"actor": actor_id, "max_items": max_items})
        client = self._client()
        run = client.actor(actor_id).call(run_input=run_input, wait_for_run=wait)
        dataset_id = getattr(run, "defaultDatasetId", None) or getattr(run, "default_dataset_id", None)
        if not dataset_id:
            return []
        items = list(client.dataset(dataset_id).iterate_items(limit=max_items))
        _log.info("daum news actor fetched", extra={"items": len(items)})
        return items

    def to_news_items(self, raw_items: list[dict]) -> list[NewsItem]:
        """Map raw Daum dataset items to normalized NewsItem rows."""
        out: list[NewsItem] = []
        for item in raw_items or []:
            if not isinstance(item, dict):
                continue
            payload = item.get("item", item)
            if not isinstance(payload, dict):
                payload = item
            content = clean_text(payload.get("body") or payload.get("description"))
            if not content:
                continue
            published = parse_timestamp(payload.get("publishedAt"))
            url = payload.get("url")
            uhash = url_hash(url) if url else sha256_hex(content)
            out.append(NewsItem(
                url=url,
                url_hash=uhash,
                title=clean_text(payload.get("title")),
                body=content,
                published_at=published,
                author=payload.get("reporter"),
                source=payload.get("publisher"),
                external_id=str(payload.get("id")) if payload.get("id") is not None else None,
            ))
        return out
