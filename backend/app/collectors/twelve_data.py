"""Twelve Data — concrete market-data provider (Phase 5).

Built against the *confirmed live response schema* (verified 2026-11-08 with a
bounded, non-persisting probe):

- ``GET https://api.twelvedata.com/time_series?symbol=&interval=1day&param=
  open,high,low,close,volume&outputsize=&start_date=&end_date=&timezone=&apikey=``
- success: ``{"status": "ok", "meta": {..., "exchange_timezone": ...},
  "values": [{"datetime": "2026-11-06", "open": "…", "high": "…", "low": "…",
  "close": "…", "volume": "…"}, …]}``  (numeric fields are strings)
- error:   ``{"status": "error", "code": 404, "message": "…"}``

Live coverage recorded (see docs/PROVIDER_COVERAGE.md): US symbols resolve;
HKEX is plan-gated ("available starting with the Grow or Venture plan"); KRX
resolution was rate-limited (8 credits/min) before it could be confirmed. Those
outcomes are *reported*, not hard-coded here — the adapter simply classifies
whatever the API returns.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import httpx

from app.collectors.exceptions import (
    AuthError,
    RateLimitError,
    SymbolNotFoundError,
    TransientError,
    InvalidResponseError,
    ProviderUnavailableError,
)
from app.collectors.normalize import normalize_symbol, ohlv_to_price_row
from app.collectors.provider import MarketDataProvider, PriceRow
from app.collectors.retry import bounded_retry
from app.core import config as config_mod
from app.core.logging import get_logger

_log = get_logger("collectors.twelvedata")

#: IANA session timezone per exchange, for the provider's ``timezone`` param.
_EXCHANGE_TZ = {"HKEX": "Asia/Hong_Kong", "KRX": "Asia/Seoul"}

_API = "https://api.twelvedata.com/time_series"
_PARAMS = "open,high,low,close,volume"


class TwelveDataProvider(MarketDataProvider):
    """Daily OHLCV from Twelve Data.

    ``client`` is injectable so tests exercise the response-parsing / error
    classification without any network. ``api_key`` defaults to the configured
    value and is never logged (requests carry it in the query string; this
    module never logs full URLs or the key).
    """

    provider_name = "twelvedata"

    def __init__(
        self,
        ticker: str,
        start: date,
        end: date,
        *,
        exchange: Optional[str] = None,
        settings: Optional[config_mod.Settings] = None,
        api_key: Optional[str] = None,
        client: Optional[httpx.Client] = None,
        timeout: Optional[float] = None,
    ) -> None:
        super().__init__(ticker, start, end)
        self.exchange = exchange
        self._settings = settings or config_mod.get_settings()
        self._client = client  # None -> build our own per call
        self._timeout = timeout if timeout is not None else self._settings.provider_timeout_seconds
        resolved = api_key
        if resolved is None:
            key = self._settings.twelve_data_api_key
            resolved = key.get_secret_value() if key else None
        self._api_key = resolved

    # -- response classification --------------------------------------------
    def _classify_response(self, resp: httpx.Response) -> list[dict]:
        """Turn an httpx response into the ``values`` list, raising on error."""
        status = resp.status_code
        if status in (401, 403):
            raise AuthError(f"Twelve Data rejected the credential (HTTP {status})")
        if status == 429:
            raise RateLimitError(
                "Twelve Data rate limit / credit exhaustion (HTTP 429)",
                status=status,
            )
        if status >= 500:
            raise TransientError(f"Twelve Data server error (HTTP {status})", status=status)
        if status == 404:
            body = self._safe_body(resp)
            msg = str(body.get("message", "")) if isinstance(body, dict) else ""
            # Plan-gated / unknown symbol both surface as 404.
            raise SymbolNotFoundError(msg or "symbol not found / not covered on plan", status=404)
        if status >= 400:
            raise ProviderUnavailableError(f"unexpected HTTP {status}", status=status)

        body = self._safe_body(resp)
        if not isinstance(body, dict):
            raise InvalidResponseError("non-JSON Twelve Data body")
        status_flag = body.get("status")
        if status_flag == "error" or body.get("code") not in (None, 200):
            msg = body.get("message", "unknown provider error")
            code = body.get("code")
            if code in (401, 403):
                raise AuthError(str(msg), status=code)
            if code in (429,):
                raise RateLimitError(str(msg), status=code)
            raise InvalidResponseError(f"Twelve Data error: {msg}", status=code)
        values = body.get("values")
        if values is None:
            # "ok" but no bars in window -> genuinely no data (not an error).
            return []
        if not isinstance(values, list):
            raise InvalidResponseError("'values' is not a list")
        return values

    @staticmethod
    def _safe_body(resp: httpx.Response):
        try:
            return resp.json()
        except (httpx.DecodingError, ValueError):
            return None

    # -- bar parsing ---------------------------------------------------------
    def _parse_bar(self, bar: dict) -> Optional[PriceRow]:
        if not isinstance(bar, dict):
            raise InvalidResponseError("bar is not an object")
        # datetime is the exchange session date ("YYYY-MM-DD"); open/high/low/
        # close/volume are strings. Missing values stay None (never 0).
        raw_date = bar.get("datetime") or bar.get("date") or bar.get("timestamp")
        if raw_date is None:
            raise InvalidResponseError("bar has no datetime/date/timestamp")
        o = bar.get("open")
        h = bar.get("high")
        l = bar.get("low")
        c = bar.get("close")
        vol = bar.get("volume")
        return ohlv_to_price_row(self.ticker, raw_date, o, h, l, c, vol)

    # -- public contract -----------------------------------------------------
    def get_daily_prices(self) -> list[PriceRow]:
        if not self._api_key:
            raise AuthError("TWELVE_DATA_API_KEY is not configured")

        symbol = normalize_symbol(self.ticker, self.exchange)
        if not symbol:
            raise SymbolNotFoundError("cannot derive a symbol", status=None)

        outsize = min(self._settings.provider_batch_limit, 5000)
        params = {
            "symbol": symbol,
            "interval": "1day",
            "param": _PARAMS,
            "outputsize": str(outsize),
            "start_date": self.start.isoformat(),
            "end_date": self.end.isoformat(),
            "timezone": _EXCHANGE_TZ.get(self.exchange, "America/New_York"),
            "apikey": self._api_key,
        }

        def _do() -> list[dict]:
            # Build a fresh client unless one was injected (keeps tests hermetic).
            if self._client is not None:
                resp = self._client.get(_API, params=params)
                return self._classify_response(resp)
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(_API, params=params)
                return self._classify_response(resp)

        values = bounded_retry(_do, settings=self._settings)
        rows: list[PriceRow] = []
        for bar in values:
            rows.append(self._parse_bar(bar))
        rows.sort(key=lambda r: r.trade_date)
        cap = self._settings.provider_batch_limit
        if len(rows) > cap:
            rows = rows[-cap:]
        _log.info(
            "twelvedata fetch",
            extra={
                "ticker": self.ticker,
                "symbol": symbol,
                "exchange": self.exchange,
                "rows": len(rows),
            },
        )
        return rows
