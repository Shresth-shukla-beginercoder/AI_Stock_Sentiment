"""Apify — social-discussion collector (Phase 5).

Built against the official ``apify_client`` SDK. The two candidate Actors are
*unverified*: before any run, :meth:`ApifySocialCollector.verify_actor` checks
that the Actor exists, is accessible to the configured account, and is not
deprecated, and captures the actual input schema + example input. Nothing here
invents Actor IDs, input fields, output fields, or successful run results.

A candidate that is unavailable / private / unsuitable is **recorded, not
silently replaced** — see the :class:`ActorAvailability` dataclass and the
``CANDIDATE_ACTORS`` registry.
"""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

import apify_client

from app.collectors.exceptions import (
    AuthError,
    ProviderError,
    TransientError,
    RateLimitError,
    ProviderUnavailableError,
)
from app.collectors.normalize import clean_text, engagement_int, parse_timestamp, social_content_hash
from app.core import config as config_mod
from app.core.logging import get_logger

_log = get_logger("collectors.apify")


@dataclasses.dataclass
class CandidateActor:
    """A candidate social Actor and its platform label (NOT a verified claim)."""

    ref: str  # "namespace/name"
    platform: str  # e.g. "telegram", "lihkg"
    notes: str = ""


#: Candidate Actors from the Phase 5 spec. Verification status is determined at
#: runtime by verify_actor(); they are documented here, never assumed working.
CANDIDATE_ACTORS: tuple[CandidateActor, ...] = (
    CandidateActor(
        ref="lofomachines/telegram-keyword-search-scraper",
        platform="telegram",
        notes="Candidate: Telegram keyword search. Publicness / investor-discussion "
        "relevance / input schema UNVERIFIED.",
    ),
    CandidateActor(
        ref="claude_code_reviewer/lihkg-scraper-en",
        platform="lihkg",
        notes="Candidate: Lihkg (HK forum) English. Whether it covers investor "
        "discussion for the asset universe is UNVERIFIED.",
    ),
)


@dataclasses.dataclass
class ActorAvailability:
    """Outcome of verifying one candidate Actor (honest, per-actor)."""

    ref: str
    platform: str
    available: bool
    reason: str
    actor_id: Optional[str] = None
    is_public: Optional[bool] = None
    is_deprecated: Optional[bool] = None
    input_schema: Optional[dict] = None
    example_input: Optional[object] = None


@dataclasses.dataclass
class SocialPostItem:
    """A normalized social post candidate (pre-persistence)."""

    source: str  # platform label (dedupe key partner)
    content_hash: str
    content: Optional[str]
    url: Optional[str]
    published_at: Optional[datetime]
    engagement: Optional[int]
    external_id: Optional[str] = None
    author_id: Optional[str] = None
    language: Optional[str] = None
    is_demo: bool = False


class ApifySocialCollector:
    """Verify and (only when verified + approved) run social Actors."""

    provider_name = "apify"

    def __init__(
        self,
        *,
        settings: Optional[config_mod.Settings] = None,
        token: Optional[str] = None,
        client: Optional[apify_client.ApifyClient] = None,
        run_wait_seconds: int = 120,
    ) -> None:
        self._settings = settings or config_mod.get_settings()
        self._injected = client
        self._token = token if token is not None else self._settings.apify_token()
        self._run_wait = timedelta(seconds=run_wait_seconds)

    def _client(self) -> apify_client.ApifyClient:
        if self._injected is not None:
            return self._injected
        if not self._token:
            raise AuthError("Apify credential is not configured (APIFY_API_TOKEN)")
        timeout = self._settings.provider_timeout_seconds
        return apify_client.ApifyClient(
            token=self._token,
            timeout_medium=timedelta(seconds=timeout),
            timeout_long=timedelta(seconds=max(timeout, 300)),
        )

    # -- verification (read-only, no run) ----------------------------------
    def verify_actor(self, ref: str, platform: Optional[str] = None) -> ActorAvailability:
        """Confirm an Actor exists / is accessible / its input schema. No run."""
        client = self._client()
        actor = client.actor(ref)
        try:
            info = actor.get()
        except AuthError:
            raise
        except Exception as e:
            msg = str(e).lower()
            if any(t in msg for t in ("401", "403", "unauthorized", "token")):
                return ActorAvailability(ref, platform or "unknown", False,
                                          f"access denied to Actor '{ref}' (auth/permission)")
            if any(t in msg for t in ("404", "not found", "does not exist")):
                return ActorAvailability(ref, platform or "unknown", False,
                                          f"Actor '{ref}' not found or not accessible")
            return ActorAvailability(ref, platform or "unknown", False,
                                     f"could not fetch Actor metadata: {e}")

        if info is None:
            return ActorAvailability(ref, platform or "unknown", False,
                                     "Actor metadata returned empty")

        is_public = getattr(info, "is_public", None)
        is_dep = getattr(info, "is_deprecated", None)
        versions = getattr(info, "versions", None) or []
        input_schema = None
        for v in versions:
            # The default/latest version carries the input schema.
            schema = getattr(v, "input_schema", None)
            if isinstance(schema, dict):
                input_schema = schema
                break

        # SDK 3.x exposes the actor's own example input as an ExampleRunInput
        # model whose ``body`` is the JSON-serialized sample (or the raw string
        # for non-JSON types). Parse it so build_run_input can work from the
        # actor's OWN documented example — nothing is invented here.
        example_input: Optional[dict] = None
        example = getattr(info, "example_run_input", None)
        body = getattr(example, "body", None)
        if isinstance(body, str) and body.strip():
            try:
                parsed = json.loads(body)
            except (json.JSONDecodeError, ValueError):
                parsed = None
            if isinstance(parsed, dict):
                example_input = parsed

        reason = "available"
        if is_dep:
            reason = "available but DEPRECATED"
        _log.info("apify actor verified",
                  extra={"actor": ref, "public": is_public, "deprecated": is_dep})
        return ActorAvailability(
            ref=ref,
            platform=platform or "unknown",
            available=True,
            reason=reason,
            actor_id=getattr(info, "id", None),
            is_public=is_public,
            is_deprecated=is_dep,
            input_schema=input_schema,
            example_input=example_input,
        )

    # -- run (only when verified + asset approved) -------------------------
    def run_actor(
        self,
        ref: str,
        run_input: dict,
        *,
        wait: Optional[timedelta] = None,
        max_items: Optional[int] = None,
        max_total_charge_usd: Optional[float] = None,
    ) -> "apify_client._resource_clients.actor.Run":
        client = self._client()
        actor = client.actor(ref)
        if not actor.validate_input(run_input):
            from app.collectors.exceptions import InvalidResponseError

            raise InvalidResponseError(
                f"run input failed Actor '{ref}' schema validation (UNVERIFIED schema — do not guess fields)"
            )
        kwargs: dict = {"run_input": run_input}
        # apify_client 3.x expresses the run wait as ``wait_duration`` (a
        # timedelta; it is added to now() to compute the poll deadline), not
        # the legacy ``wait_for_run``. Optional caps keep a run bounded and
        # cost-capped (existing credits only — never a purchase/plan change).
        wait_td = wait or self._run_wait
        kwargs["wait_duration"] = wait_td
        if max_items is not None:
            kwargs["max_items"] = max_items
        if max_total_charge_usd is not None:
            kwargs["max_total_charge_usd"] = max_total_charge_usd
        run = actor.call(**kwargs)
        if run is None:
            raise ProviderUnavailableError(f"Apify run did not start for '{ref}'")
        return run

    def fetch_items(self, run, *, limit: Optional[int] = None,
                    offset: int = 0) -> list[dict]:
        """Read dataset items from a completed run (bounded)."""
        client = self._client()
        dataset_id = getattr(run, "default_dataset_id", None)
        if not dataset_id:
            return []
        cap = limit or self._settings.provider_batch_limit
        page = client.dataset(dataset_id).list_items(limit=cap, offset=offset)
        items = getattr(page, "items", None) or []
        return items

    # -- output mapping (tolerant; UNVERIFIED schema) ----------------------
    def to_social_items(self, raw_items: list[dict], *, platform: str) -> list[SocialPostItem]:
        """Map raw Actor output items to normalized posts.

        Output fields are UNVERIFIED, so this is a *tolerant* mapper: it looks
        for common field spellings and keeps whatever is present, leaving gaps
        as NULL. It never fabricates text or ids.
        """
        out: list[SocialPostItem] = []
        for idx, raw in enumerate(raw_items or []):
            if not isinstance(raw, dict):
                continue
            item = raw.get("item", raw)  # Apify often wraps payloads under 'item'
            if not isinstance(item, dict):
                item = raw

            def pick(*keys, default=None):
                for k in keys:
                    if k in item and item[k] not in (None, ""):
                        return item[k]
                return default

            external_id = pick("id", "postId", "post_id", "messageId", "message_id")
            text = pick("text", "message", "content", "body", "post_text")
            text = clean_text(str(text)) if text is not None else None
            if text is None:
                # No usable discussion text -> not a social post we can keep.
                continue
            url = pick("url", "link", "postUrl", "permalink")
            published = parse_timestamp(pick("date", "createdAt", "created_at",
                                             "timestamp", "publishedAt", "published_at"))
            engagement = engagement_int(pick("likes", "reactions", "likesCount",
                                             "reactionsCount", "engagements", "upvotes"))
            author = pick("user", "author", "sender", "from", "username")
            author_id = author if isinstance(author, str) else None

            chash = social_content_hash(platform, text, str(external_id) if external_id is not None else None)
            out.append(SocialPostItem(
                source=platform,
                content_hash=chash,
                content=text,
                url=str(url) if url is not None else None,
                published_at=published,
                engagement=engagement,
                external_id=str(external_id) if external_id is not None else None,
                author_id=author_id,
                language=None,  # detected in Phase 6, never inferred here
            ))
        _log.info("apify items mapped", extra={"platform": platform, "items": len(out)})
        return out


# ---------------------------------------------------------------------------
# W1: config-driven actor execution
# ---------------------------------------------------------------------------

#: Per-exchange platform -> Settings field holding the owner-supplied Actor ref.
#: An empty ref means "not configured" for that exchange: the worker records it
#: honestly and never invents an Actor id.
EXCHANGE_ACTOR_FIELDS: dict[str, tuple[tuple[str, str], ...]] = {
    "HKEX": (("lihkg", "apify_actor_lihkg"), ("telegram", "apify_actor_telegram")),
    "KRX": (("kakao", "apify_actor_kakao"), ("naver", "apify_actor_naver")),
}

#: String schema/example keys whose value is a *searchable ticker/keyword*.
#: Only these may be filled with the ticker; any other field is left untouched
#: or the input is declared not safely constructible.
_QUERY_KEY_HINTS = ("keyword", "search", "query", "channel", "ticker", "stock", "text")


def configured_actors(settings, exchange: Optional[str]) -> list[tuple[str, str]]:
    """[(platform, actor_ref)] for the exchange's configured Actor refs.

    Unknown exchanges fall back to the HKEX set only when it has refs; an
    unrecognised exchange returns whatever refs exist, honestly labelled.
    """
    exchange_key = (exchange or "").upper()
    fields = EXCHANGE_ACTOR_FIELDS.get(exchange_key, EXCHANGE_ACTOR_FIELDS.get("HKEX", ()))
    out: list[tuple[str, str]] = []
    for platform, field in fields:
        ref = getattr(settings, field, "") or ""
        out.append((platform, ref.strip()))
    return out


def build_run_input(
    availability: ActorAvailability,
    ticker: str,
) -> tuple[Optional[dict], str]:
    """Build an Actor run input WITHOUT guessing fields.

    Returns ``(input, note)`` where ``input`` is None when it cannot be built
    safely (the run is then skipped and the reason recorded).

    Strategy, in order:
    1. Actor-provided ``example_run_input`` (a dict): the actor's own
       documented example. Any query-like key that is empty gets the ticker;
       otherwise the example is used as-is.
    2. Otherwise the input schema's ``required`` string properties: query-like
       keys get the ticker. If ANY required property cannot be filled this
       way (numbers, booleans, unknown keys, e.g. a channel-username list),
       the input is declared not constructible — never invent values.
    3. No schema and no example -> not constructible.
    """
    example = availability.example_input
    if isinstance(example, dict):
        inp = dict(example)
        filled = False
        for key, value in inp.items():
            if isinstance(value, str) and not value.strip():
                lowered = str(key).lower()
                if any(h in lowered for h in _QUERY_KEY_HINTS):
                    inp[key] = ticker
                    filled = True
        note = "actor example input used" + (", query field(s) set to ticker" if filled else "")
        return inp, note

    schema = availability.input_schema or {}
    props = schema.get("properties") if isinstance(schema, dict) else None
    required = [k for k in (schema.get("required") or []) if isinstance(k, str)] if isinstance(schema, dict) else []
    if isinstance(props, dict) and required:
        inp: dict = {}
        for key in required:
            ptype = (props.get(key) or {}).get("type")
            lowered = key.lower()
            if ptype in ("string", None) and any(h in lowered for h in _QUERY_KEY_HINTS):
                inp[key] = ticker
            elif ptype in ("string", None) and key in props:
                # Non-query string with a schema default? Use it; else impossible.
                default = (props.get(key) or {}).get("default")
                if default is not None:
                    inp[key] = default
                else:
                    return None, (
                        f"required input '{key}' is not a query field and has no schema "
                        f"default — input not safely constructible (schema inspected, no guessing)"
                    )
            else:
                return None, (
                    f"required input '{key}' (type={ptype}) cannot be filled without "
                    f"guessing — input not safely constructible"
                )
        return inp, "built from schema required string properties"

    return None, "no example input and no usable input schema — input not constructible"


def resolve_exchange_actors(settings, exchange: Optional[str],
                            collector: "ApifySocialCollector",
                            ticker: str) -> list[dict]:
    """Verify each configured actor for the exchange and build a run input.

    Returns one record per configured platform:
    {platform, actor, configured, available, reason, run_input, input_note}
    Unconfigured platforms are recorded (not errors). Never raises on a
    per-actor verification problem — those are recorded.
    """
    records: list[dict] = []
    for platform, ref in configured_actors(settings, exchange):
        rec: dict = {"platform": platform, "actor": ref or None,
                     "configured": bool(ref), "available": False,
                     "reason": "not configured", "run_input": None, "input_note": None}
        if not ref:
            records.append(rec)
            continue
        try:
            avail = collector.verify_actor(ref, platform)
        except Exception as e:
            rec["reason"] = f"verify raised: {e}"
            records.append(rec)
            continue
        rec["available"] = avail.available
        rec["reason"] = avail.reason
        if avail.available:
            inp, note = build_run_input(avail, ticker)
            rec["run_input"] = inp
            rec["input_note"] = note
            if inp is None:
                rec["reason"] = f"available but {note}"
                rec["available"] = False
        records.append(rec)
    return records
