"""Pure normalization services for the collection layer.

Every function here is deterministic and side-effect free so it can be unit-
tested in isolation and reused across providers. Data rules (CLAUDE.md):

- Missing values stay ``None`` (never coerced to 0 / empty string).
- All timestamps are normalised to tz-aware UTC; naive inputs are rejected or
  handled honestly (a *publication* timestamp with no tz is coerced to UTC and
  flagged; a market *trading date* is a calendar date, not a datetime).
- Text is NFKC-normalised, HTML-stripped, and whitespace-collapsed *without*
  destroying meaningful content.
- Content hashes are SHA-256 over a stable, canonicalised byte form.
"""

from __future__ import annotations

import html
import hashlib
import re
import unicodedata
from datetime import date, datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from typing import Optional

from app.collectors.exceptions import InvalidResponseError
from app.collectors.provider import PriceRow

#: Exchanges we serve. KRX suffix is `.KS` (vendor convention for the KRX
#: main board), matching docs/PROVIDER_COVERAGE.md.
_EXCHANGE_SUFFIX = {"HKEX": ".HK", "KRX": ".KS"}
#: Digit width used when a bare code is given: HKEX 4-digit, KRX 6-digit.
_EXCHANGE_WIDTH = {"HKEX": 4, "KRX": 6}

_WS_RE = re.compile(r"\s+")


def sha256_hex(text: str) -> str:
    """Stable content hash over UTF-8 bytes. Caller controls canonical form."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def clean_text(raw: Optional[str]) -> Optional[str]:
    """NFKC-normalise, strip HTML entities/tags, collapse whitespace.

    ``None`` in -> ``None`` out (missing stays missing). An all-whitespace
    string becomes ``""`` (present but empty), never ``None``.
    """
    if raw is None:
        return None
    # Decode common entities first; unescape leaves real entities readable.
    decoded = html.unescape(raw)
    # Strip <tags>, keep the text between them (tags are not meaningful content).
    decoded = re.sub(r"<[^>]+>", " ", decoded)
    normalized = unicodedata.normalize("NFKC", decoded)
    return _WS_RE.sub(" ", normalized).strip()


def engagement_int(raw: object) -> Optional[int]:
    """Coerce provider engagement to a non-negative int, or None when missing.

    Never 0 by default: absent/invalid values are returned as ``None`` (the
    schema stores NULL for 'unknown', and weight = 1 + ln(1 + engagement)
    treats NULL as 0 at the *sentiment* stage, not here).
    """
    if raw is None:
        return None
    if isinstance(raw, bool):  # bool is an int subclass; treat as missing
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        try:
            value = int(float(raw))
        except (TypeError, ValueError):
            return None
    return value if value >= 0 else None


def parse_timestamp(raw: object) -> Optional[datetime]:
    """Parse a provider timestamp to an aware UTC ``datetime``.

    - ISO-8601 with offset -> converted to UTC.
    - Naive ISO string -> interpreted as UTC (honest coercion, documented).
    - ``None`` / unparseable -> ``None`` (missing date stays missing).
    """
    if raw is None:
        return None
    if isinstance(raw, datetime):
        dt = raw
    elif isinstance(raw, date):
        dt = datetime(raw.year, raw.month, raw.day, tzinfo=timezone.utc)
    elif isinstance(raw, (int, float)):
        # Epoch seconds (or ms for very large values).
        seconds = float(raw)
        if seconds > 1e12:  # likely milliseconds
            seconds /= 1000.0
        try:
            dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    elif isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        iso = text.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(iso)
        except ValueError:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
                try:
                    dt = datetime.strptime(text, fmt)
                    break
                except ValueError:
                    dt = None
                    break
            if dt is None:
                return None
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def canonical_url(raw: Optional[str]) -> Optional[str]:
    """Deterministic URL for dedupe + storage.

    Lower-schemes/host, drops fragments and a trailing slash, sorts the query.
    ``None`` -> ``None``.
    """
    if raw is None:
        return None
    url = raw.strip()
    if not url:
        return None
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    path = parts.path or ""
    if path.endswith("/") and len(path) > 1:
        path = path.rstrip("/")
    return urlunsplit((scheme, netloc, path, query, ""))


def url_hash(raw: Optional[str]) -> Optional[str]:
    """SHA-256 of the canonical URL — the ``news_articles.url_hash`` dedupe key."""
    canon = canonical_url(raw)
    if canon is None:
        return None
    return sha256_hex(canon)


def social_content_hash(source: str, text: Optional[str], external_id: Optional[str]) -> str:
    """Deterministic ``social_posts.content_hash``.

    Combines platform/source + external post id + normalised text so re-runs
    dedupe by 'source + external post id' with a content-hash fallback when the
    id is absent.
    """
    norm = (text or "")
    return sha256_hex(f"{source}\x00{external_id or ''}\x00{norm}")


def normalize_symbol(raw: Optional[str], exchange: Optional[str] = None) -> Optional[str]:
    """Normalise a ticker to the vendor's symbol form.

    - Already-suffixed (``0700.HK`` / ``005930.KS``): upper-cased, kept as-is.
    - Bare code + exchange known: zero-padded to the exchange width + suffix.
    - Bare code, no exchange: upper-cased as given (best effort).
    - ``None`` -> ``None``.
    """
    if raw is None:
        return None
    code = raw.strip().upper()
    if "." in code:
        return code
    if exchange in _EXCHANGE_SUFFIX:
        width = _EXCHANGE_WIDTH[exchange]
        padded = code.zfill(width)
        return f"{padded}{_EXCHANGE_SUFFIX[exchange]}"
    return code


def _coerce_price(value: object, field: str) -> Optional[float]:
    """Numeric OHLC field -> float, or None when missing. Malformed -> error."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise InvalidResponseError(f"non-numeric {field} value: {value!r}")


def ohlv_to_price_row(
    ticker: str,
    session_date: object,
    open_: object,
    high: object,
    low: object,
    close: object,
    volume: object = None,
) -> PriceRow:
    """Validate an OHLCV tuple and build a ``PriceRow``.

    - Missing OHLC is a *hard* data error (a bar must have a close); missing
      volume stays ``None``.
    - ``session_date`` is the exchange-local trading day (date, or a provider
      datetime we reduce to its UTC date). Naive provider datetimes are treated
      as the trading calendar date, not as a time-of-day.
    - Rejects an impossible bar (high < low, high < open/close, low > open/close)
      but keeps NULL volume.
    """
    if isinstance(session_date, datetime):
        trading_date = session_date.date()
    elif isinstance(session_date, date):
        trading_date = session_date
    else:
        parsed = parse_timestamp(session_date)
        if parsed is None:
            raise InvalidResponseError(f"unparseable trading date: {session_date!r}")
        trading_date = parsed.date()

    o = _coerce_price(open_, "open")
    h = _coerce_price(high, "high")
    l = _coerce_price(low, "low")
    c = _coerce_price(close, "close")
    if c is None:
        raise InvalidResponseError("close is required for a price bar")

    # Price-order sanity: a sane bar has high >= max(open,close) >= min(open,close)
    # >= low. Missing open/high/low are allowed to stay None (NULL) but any
    # present one that contradicts close is malformed.
    present = [v for v in (o, h, l, c) if v is not None]
    if present:
        if h is not None and (o is not None and h < o or h < c):
            raise InvalidResponseError(f"high below open/close: {h} < {o}/{c}")
        if l is not None and (o is not None and l > o or l > c):
            raise InvalidResponseError(f"low above open/close: {l} > {o}/{c}")

    vol = None
    if volume is not None and volume != "":
        try:
            vol = int(float(volume))
        except (TypeError, ValueError):
            vol = None  # malformed volume -> unknown, not 0

    # PriceRow requires an aware-UTC trade_date. Use the trading day's UTC
    # midnight; features (Phase 8) own exchange-specific session timing.
    # Missing open/high/low stay None (NULL), never coerced to 0.
    trade_dt = datetime(trading_date.year, trading_date.month, trading_date.day,
                        tzinfo=timezone.utc)
    return PriceRow(
        ticker=ticker,
        trade_date=trade_dt,
        open=o,
        high=h,
        low=l,
        close=c,
        volume=vol,
    )
