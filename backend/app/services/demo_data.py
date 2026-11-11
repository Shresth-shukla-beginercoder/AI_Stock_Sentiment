"""Deterministic, fully synthetic demo dataset for API testing.

Hard rules (Phase 3 spec + CLAUDE.md):
- Isolated synthetic identifiers only: DEMO-HK-001 / DEMO-KR-001 on exchange
  "DEMO". NEVER real HKEX/KRX tickers, never real company names.
- Every record carries is_demo=True; every response carries data_mode="demo"
  and meta.source="demo-synthetic".
- Fully reproducible: generated from fixed constants, no wall-clock inputs.
- Missing values stay None (never 0 / fabricated fallbacks).
- Demo and live data never mix in one response.
"""

from __future__ import annotations

import hashlib
import math
from datetime import date, datetime, timezone
from typing import Any

# --- fixed synthetic universe -------------------------------------------------
DEMO_TICKERS: tuple[str, ...] = ("DEMO-HK-001", "DEMO-KR-001")
DEMO_EXCHANGE = "DEMO"
DEMO_PROVIDER = "synthetic"  # no real provider is used for demo data

ASSETS: list[dict[str, Any]] = [
    {
        "id": 1,
        "exchange": DEMO_EXCHANGE,
        "ticker": "DEMO-HK-001",
        "name": "Synthetic Demo Asset (HK-style)",
        "provider_ticker": None,  # synthetic: deliberately no provider symbol
        "provider_symbol_format": None,
        "market_data_provider": DEMO_PROVIDER,
        "confirmed": False,
        "active": True,
        "is_demo": True,
        "synthetic": True,
    },
    {
        "id": 2,
        "exchange": DEMO_EXCHANGE,
        "ticker": "DEMO-KR-001",
        "name": "Synthetic Demo Asset (KR-style)",
        "provider_ticker": None,
        "provider_symbol_format": None,
        "market_data_provider": DEMO_PROVIDER,
        "confirmed": False,
        "active": True,
        "is_demo": True,
        "synthetic": True,
    },
]

# Fixed anchor: deterministic outputs, no wall-clock dependence.
_DEMO_AS_OF = datetime(2026, 11, 2, 16, 0, 0, tzinfo=timezone.utc)
_PRICE_START = date(2026, 10, 3)
_PRICE_DAYS = 30
_POSTS_PER_TIKER = 24
_NEWS_PER_TIKER = 12

# --- price series: seeded random walk -----------------------------------------
def _price_series(ticker: str) -> list[dict[str, Any]]:
    """Deterministic OHLCV walk. Reproducible from the ticker alone."""
    seed = int(hashlib.sha256(ticker.encode()).hexdigest()[:8], 16) % 100_000
    base = 80.0 + (seed % 120)
    step = (seed % 17) / 10.0 - 0.8  # in [-0.8, +0.8]
    rows: list[dict[str, Any]] = []
    close = base
    for i in range(_PRICE_DAYS):
        day = _PRICE_START.fromordinal(_PRICE_START.toordinal() + i)
        open_ = close
        high = max(open_, close) * 1.004
        low = min(open_, close) * 0.996
        close = round(open_ + step, 4)
        volume = None if i % 9 == 8 else 1_000_000 + i * 7_321  # NULL = unknown day
        rows.append(
            {
                "trade_date": day.isoformat(),
                "provider": DEMO_PROVIDER,
                "open": round(open_, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": close,
                "volume": volume,
                "is_demo": True,
            }
        )
    return rows


# --- social posts: deterministic synthetic content ----------------------------
def _demo_posts(ticker: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    labels = ["positive", "neutral", "negative", "neutral"]
    for i in range(_POSTS_PER_TIKER):
        published = _DEMO_AS_OF.fromtimestamp(_DEMO_AS_OF.timestamp() - i * 4 * 3600)
        engagement = None if i % 7 == 6 else 5 * (i + 1)  # missing => NULL, never 0
        rows.append(
            {
                "id": i + 1,
                "asset_ticker": ticker,
                "source": "demo-social.example",
                "content_hash": hashlib.sha256(f"{ticker}:{i}".encode()).hexdigest(),
                "content": f"[synthetic demo post #{i + 1} for {ticker}] simulated chatter only",
                "language": "en" if i % 2 == 0 else None,  # unknown => NULL
                "url": f"https://demo-social.example/{ticker}/{i + 1}",
                "published_at": published.isoformat(),
                "engagement": engagement,
                "is_demo": True,
                "sentiment_label": labels[i % 4],
            }
        )
    return rows


# --- news: clearly labelled synthetic headlines --------------------------------
def _demo_news(ticker: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    labels = ["neutral", "positive", "neutral", "negative"]
    for i in range(_NEWS_PER_TIKER):
        published = _DEMO_AS_OF.fromtimestamp(_DEMO_AS_OF.timestamp() - (i + 1) * 9 * 3600)
        rows.append(
            {
                "id": i + 1,
                "asset_ticker": ticker,
                "source": "demo-news.example",
                "url_hash": hashlib.sha256(f"{ticker}:news:{i}".encode()).hexdigest(),
                "title": f"[synthetic demo headline #{i + 1}] simulated market note for {ticker}",
                "body": None if i % 5 == 4 else f"Simulated demo text, no real-world claims ({i + 1}).",
                "url": f"https://demo-news.example/{ticker}/{i + 1}",
                "published_at": published.isoformat(),
                "is_demo": True,
                "sentiment_label": labels[i % 4],
            }
        )
    return rows


# --- sentiment aggregate (CLAUDE.md formula) ----------------------------------
def _demo_sentiment(ticker: str) -> dict[str, Any]:
    """Deterministic aggregate following the CLAUDE.md formula:
    score = P(pos) - P(neg); weight = 1 + ln(1 + engagement) (missing => 0).
    10-day window around the demo anchor.
    """
    posts = _demo_posts(ticker)
    news = _demo_news(ticker)
    items = [p | {"kind": "post"} for p in posts] + [n | {"kind": "news"} for n in news]
    by_label = {"positive": 0, "neutral": 0, "negative": 0}
    for it in items:
        by_label[it["sentiment_label"]] += 1
    total = len(items)
    p_pos = by_label["positive"] / total
    p_neu = by_label["neutral"] / total
    p_neg = by_label["negative"] / total
    score = round(p_pos - p_neg, 6)
    # combined weighting: 0.4 social + 0.6 news (configurable constant)
    social_w = sum(1 + math.log1p(5 * (i + 1)) if i % 7 != 6 else 0 for i in range(len(posts)))
    state = "sufficient" if total >= 5 else "insufficient_data"
    return {
        "asset_ticker": ticker,
        "window_days": 10,
        "as_of": _DEMO_AS_OF.isoformat(),
        "counts": by_label,
        "total_items": total,
        "p_pos": round(p_pos, 6),
        "p_neu": round(p_neu, 6),
        "p_neg": round(p_neg, 6),
        "score": score,  # P(pos) - P(neg)
        "signal": "positive" if score > 0.15 else "negative" if score < -0.15 else "neutral",
        "state": state,
        "social_weight": round(0.4 * social_w, 4),
        "note": "Synthetic demo aggregate — not a real sentiment result.",
        "is_demo": True,
    }


# --- predictions: experimental, clearly synthetic -----------------------------
def _demo_predictions(ticker: str) -> list[dict[str, Any]]:
    last = _price_series(ticker)[-1]
    made = _DEMO_AS_OF.fromtimestamp(_DEMO_AS_OF.timestamp() + 86_400)
    return [
        {
            "id": 1,
            "asset_ticker": ticker,
            "model_version": "demo-v0",
            "target_date": (_PRICE_START.fromordinal(_PRICE_START.toordinal() + _PRICE_DAYS)).isoformat(),
            "made_at": made.isoformat(),
            "predicted_return": 0.0012,
            "predicted_price": round(last["close"] * 1.0012, 4),
            "actual_close": None,  # backfilled later; NULL until then
            "experimental": True,
            "is_demo": True,
            "note": "Synthetic demo prediction — experimental, not financial advice.",
        }
    ]


# --- model evaluations: synthetic metrics with NULLs where unknown ------------
def _demo_evaluations() -> list[dict[str, Any]]:
    return [
        {
            "id": 1,
            "model_version": "synthetic-v0",
            "mae": 0.0041,
            "rmse": 0.0058,
            "directional_accuracy": 0.548,
            "baseline_nochange_mae": 0.0043,
            "baseline_nochange_rmse": 0.0060,
            "baseline_nochange_dir_acc": 0.52,
            "baseline_alwaysup_dir_acc": 0.48,
            "n_test": 64,
            "params": {"model": "ridge", "alpha": 1.0},
            "git_commit": None,  # unknown for synthetic records — never invented
            "trained_at": _DEMO_AS_OF.isoformat(),
            "is_demo": True,
            "note": "Synthetic demo metrics — not from a real training run.",
        },
        {
            "id": 2,
            "model_version": "synthetic-v1",
            "mae": 0.0038,
            "rmse": 0.0055,
            "directional_accuracy": 0.561,
            "baseline_nochange_mae": 0.0043,
            "baseline_nochange_rmse": 0.0060,
            "baseline_nochange_dir_acc": 0.52,
            "baseline_alwaysup_dir_acc": 0.48,
            "n_test": 64,
            "params": {"model": "ridge", "alpha": 0.5},
            "git_commit": None,
            "trained_at": _DEMO_AS_OF.fromtimestamp(_DEMO_AS_OF.timestamp() + 43_200).isoformat(),
            "is_demo": True,
            "note": "Synthetic demo metrics — not from a real training run.",
        },
    ]


# --- accessors -----------------------------------------------------------------
def get_asset(ticker: str) -> dict[str, Any] | None:
    return next((a for a in ASSETS if a["ticker"] == ticker), None)


def list_assets() -> list[dict[str, Any]]:
    return list(ASSETS)


def get_posts(ticker: str) -> list[dict[str, Any]]:
    return _demo_posts(ticker)


def get_news(ticker: str) -> list[dict[str, Any]]:
    return _demo_news(ticker)


def get_prices(ticker: str) -> list[dict[str, Any]]:
    return _price_series(ticker)


def get_sentiment(ticker: str) -> dict[str, Any]:
    return _demo_sentiment(ticker)


def get_predictions(ticker: str) -> list[dict[str, Any]]:
    return _demo_predictions(ticker)


def get_evaluations() -> list[dict[str, Any]]:
    return _demo_evaluations()


def get_overview() -> dict[str, Any]:
    """Whole-universe dashboard payload (demo)."""
    per_ticker = {}
    for t in DEMO_TICKERS:
        sent = _demo_sentiment(t)
        per_ticker[t] = {
            "name": next(a["name"] for a in ASSETS if a["ticker"] == t),
            "posts": len(_demo_posts(t)),
            "news": len(_demo_news(t)),
            "price_days": len(_price_series(t)),
            "sentiment_score": sent["score"],
            "sentiment_signal": sent["signal"],
            "state": sent["state"],
        }
    return {
        "universe": [a["ticker"] for a in ASSETS],
        "per_ticker": per_ticker,
        "models": [e["model_version"] for e in _demo_evaluations()],
        "note": "Synthetic demo overview — not real market performance.",
        "is_demo": True,
    }


def get_ranking() -> list[dict[str, Any]]:
    """Assets ranked by demo sentiment score, best first."""
    ranked = sorted(
        ({"ticker": a["ticker"], "name": a["name"], "score": _demo_sentiment(a["ticker"])["score"]}
         for a in ASSETS),
        key=lambda r: r["score"],
        reverse=True,
    )
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
    return ranked


# --- per-ticker report (W5 parity with the live report) ----------------------
_DEMO_SR_WINDOW = 20  # mirrors settings.support_resistance_window_sessions


def _demo_levels(ticker: str) -> dict[str, Any]:
    """Window-extremes S/R over the demo price walk (same rule as W4)."""
    rows = _price_series(ticker)[-_DEMO_SR_WINDOW:]
    usable = [r for r in rows if r["low"] is not None or r["high"] is not None]
    lows = [r["low"] for r in usable if r["low"] is not None]
    highs = [r["high"] for r in usable if r["high"] is not None]
    sufficient = len(usable) >= 2
    return {
        "support": min(lows) if lows else None,
        "resistance": max(highs) if highs else None,
        "method": "window_extremes: support=min(low), resistance=max(high) over the most recent "
                  f"{_DEMO_SR_WINDOW} stored trading sessions (actual bars used: {len(rows)})",
        "window_sessions": _DEMO_SR_WINDOW,
        "available_sessions": len(rows),
        "data_sufficient": sufficient,
        "as_of": rows[-1]["trade_date"] if rows else None,
        "basis": "deterministic synthetic price walk (demo)",
    }


def _demo_position(close: Any, sr: dict[str, Any]) -> str:
    if close is None or not sr["data_sufficient"]:
        return "unknown"
    if close > sr["resistance"]:
        return "above_resistance"
    if close < sr["support"]:
        return "below_support"
    return "between"


def get_ticker_report() -> dict[str, Any]:
    """Demo per-ticker, exchange-separated report — SAME shape as the live
    report (W5: the API and the frontend represent the same report data).
    All values derive from the deterministic demo dataset; nothing is live.
    """
    by_exchange: dict[str, list[dict[str, Any]]] = {}
    for a in ASSETS:
        t = a["ticker"]
        prices = _price_series(t)
        last_price = prices[-1] if prices else None
        sent = _demo_sentiment(t)
        preds = _demo_predictions(t)
        pred = preds[0] if preds else None
        pred_ret = pred["predicted_return"] if pred else None
        if pred_ret is None:
            direction = "none"
        elif pred_ret > 0:
            direction = "up"
        elif pred_ret < 0:
            direction = "down"
        else:
            direction = "flat"
        sr = _demo_levels(t)
        posts, news = len(_demo_posts(t)), len(_demo_news(t))
        close = last_price["close"] if last_price else None
        row = {
            "ticker": t,
            "name": a["name"],
            "current_price": (
                {"close": last_price["close"], "provider": last_price["provider"],
                 "trade_date": last_price["trade_date"]}
                if last_price else None
            ),
            "sentiment": {"score": sent["score"], "signal": sent["signal"], "state": sent["state"]},
            "direction": direction,
            "prediction": {
                "model_version": pred["model_version"],
                "target_date": pred["target_date"],
                "predicted_return": pred["predicted_return"],
                "predicted_price": pred["predicted_price"],
                "actual_close": pred["actual_close"],
                "experimental": pred["experimental"],
                "direction": direction,
            } if pred else None,
            "support_resistance": sr,
            "position": _demo_position(close, sr),
            "mentions": {"social_posts": posts, "news_articles": news, "total": posts + news},
            "is_demo": True,
        }
        by_exchange.setdefault(a["exchange"], []).append(row)

    exchanges = []
    for ex in sorted(by_exchange):
        rows = sorted(
            by_exchange[ex],
            key=lambda r: (
                -r["mentions"]["total"],
                r["sentiment"]["score"] is None,
                -(r["sentiment"]["score"] or 0.0),
                r["ticker"],
            ),
        )
        for i, r in enumerate(rows, 1):
            r["rank"] = i
        exchanges.append({"exchange": ex, "timezone": "UTC", "tickers": rows})

    ranking = [r for ex in exchanges for r in ex["tickers"]]
    return {
        "as_of": _DEMO_AS_OF.isoformat(),
        "exchanges": exchanges,
        "ranking": ranking,
        "meta": {
            "generated_at": _DEMO_AS_OF.isoformat(),
            "ranking_rule": "total mentions desc, then sentiment score desc (None last), then ticker asc — within each exchange",
            "sentiment_thresholds": {
                "bullish": 0.15, "bearish": -0.15, "min_items": 5, "window_days": 10,
            },
            "support_resistance_window_sessions": _DEMO_SR_WINDOW,
            "direction_rule": "sign of the latest stored prediction's predicted_return",
            "missing_policy": "null = not yet known / no data stored; 0 = a real count of zero",
            "note": "Synthetic demo report — not real market data.",
        },
    }
