"""Manual / CLI collection runner for Phase 5.

Phase 5 is *reusable provider clients + collector services + controlled
manual execution* — not a background worker (that is Phase 7). This script is
how a human (or the Phase 7 worker, later) drives a bounded collection run.

Subcommands
-----------
probe-market    Fetch + normalize prices, print a summary. NO persistence.
probe-news      Run one news search, print a summary. NO persistence.
verify-actors   Check each candidate Apify Actor exists / is accessible. NO run.
collect-market  Fetch + persist prices for an *approved* asset (gated).
collect-news    Search + persist news for an asset (gated on a real asset row).
collect-social  Run + persist a verified Actor for an asset (gated).

The collect-* paths refuse to touch data for tickers that have no ``assets``
row (or that are not confirmed), because the 10 proposed tickers are PENDING
the user's explicit confirmation. Probes are read-only and never persist.

Run from the ``backend/`` directory::

    python -m app.scripts.collect probe-market --ticker 0700 --exchange HKEX --days 5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, timedelta

from dotenv import load_dotenv

# Load the repo-root .env so real credentials are available locally (never
# printed). Real environment variables still take precedence.
_ENV = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))
if os.path.exists(_ENV):
    load_dotenv(_ENV)

from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging  # noqa: E402


_log = get_logger("scripts.collect")


def _days_back(n: int) -> tuple[date, date]:
    end = date.today()
    return end - timedelta(days=n), end


def _print(obj, **kw) -> None:
    print(json.dumps(obj, default=str, indent=2, **kw))


# ------------------------------------------------------------------ probes
def probe_market(args) -> int:
    from app.collectors.twelve_data import TwelveDataProvider
    from app.collectors.exceptions import ProviderError

    settings = get_settings()
    start, end = _days_back(args.days)
    provider = TwelveDataProvider(
        args.ticker, start, end, exchange=args.exchange, settings=settings
    )
    _log.info("probe market start", extra={"ticker": args.ticker, "exchange": args.exchange})
    try:
        rows = provider.get_daily_prices()
    except ProviderError as e:
        print(f"RESULT: provider_error category={e.category} message={e.message!r}")
        return 0  # an honest provider error is a valid probe outcome, not a crash
    except Exception as e:  # unexpected
        print(f"RESULT: unexpected_error {type(e).__name__}: {e}")
        return 1
    if not rows:
        print("RESULT: ok rows=0 (no data in window — not an error)")
        return 0
    _print({
        "result": "ok",
        "provider": provider.provider_name,
        "rows": len(rows),
        "first": rows[0].trade_date.date().isoformat(),
        "last": rows[-1].trade_date.date().isoformat(),
        "first_close": rows[0].close,
        "last_close": rows[-1].close,
        "null_volume_count": sum(1 for r in rows if r.volume is None),
    })
    print("NOTE: probe only — nothing persisted. No asset approval was required.")
    return 0


def probe_news(args) -> int:
    from app.collectors.exa import ExaNewsCollector
    from app.collectors.exceptions import ProviderError

    settings = get_settings()
    coll = ExaNewsCollector(settings=settings)
    query = args.query or (f"{args.ticker} financial news" if args.ticker else "financial news")
    try:
        items = coll.search(
            query, days=args.days, include_domains=args.domains.split(",") if args.domains else None,
        )
    except ProviderError as e:
        print(f"RESULT: provider_error category={e.category} message={e.message!r}")
        return 0
    except Exception as e:
        print(f"RESULT: unexpected_error {type(e).__name__}: {e}")
        return 1
    _print({
        "result": "ok",
        "provider": "exa",
        "items": len(items),
        "with_missing_date": sum(1 for i in items if i.published_at is None),
        "sample_titles": [i.title for i in items[:5]],
    })
    print("NOTE: probe only — nothing persisted.")
    return 0


def verify_actors(args) -> int:
    from app.collectors.apify import ApifySocialCollector, CANDIDATE_ACTORS
    from app.collectors.exceptions import ProviderError

    settings = get_settings()
    coll = ApifySocialCollector(settings=settings)
    for cand in CANDIDATE_ACTORS:
        try:
            avail = coll.verify_actor(cand.ref, platform=cand.platform)
            _print({
                "actor": cand.ref,
                "platform": cand.platform,
                "available": avail.available,
                "reason": avail.reason,
                "is_public": avail.is_public,
                "is_deprecated": avail.is_deprecated,
                "has_input_schema": avail.input_schema is not None,
                "notes": cand.notes,
            })
        except ProviderError as e:
            _print({"actor": cand.ref, "platform": cand.platform,
                    "available": False, "reason": f"{e.category}: {e.message}"})
    print("NOTE: verification only — no Actor was run, no social data collected.")
    return 0


# ---------------------------------------------------------------- collect
def _require_asset(ticker: str, exchange: str | None, settings):
    """Resolve an asset row for persistence; refuse when missing / unconfirmed."""
    from app.database.session import get_session_factory
    from app.services.persist import resolve_asset

    factory = get_session_factory()
    with factory() as session:
        asset = resolve_asset(session, ticker, exchange)
        if asset is None:
            print(f"REFUSED: no 'assets' row for ticker {ticker!r}. "
                  f"Pending tickers are not seeded until the user confirms them.")
            return None, 0
        if not asset.confirmed:
            print(f"REFUSED: asset {asset.exchange}:{asset.ticker} is not confirmed "
                  f"(confirmed=false). Persisting production data for a pending "
                  f"ticker is not allowed until the user approves it.")
            return None, 0
        return asset, asset.id


def collect_market(args) -> int:
    settings = get_settings()
    asset, asset_id = _require_asset(args.ticker, args.exchange, settings)
    if asset is None:
        return 2
    from app.collectors.twelve_data import TwelveDataProvider
    from app.collectors.exceptions import ProviderError
    from app.services.persist import persist_market_prices
    from app.database.session import get_session_factory

    start, end = _days_back(args.days)
    provider = TwelveDataProvider(args.ticker, start, end,
                                  exchange=args.exchange or asset.exchange,
                                  settings=settings)
    try:
        rows = provider.get_daily_prices()
    except ProviderError as e:
        print(f"RESULT: provider_error category={e.category} message={e.message!r}")
        return 0
    factory = get_session_factory()
    with factory() as session:
        res = persist_market_prices(session, asset_id, provider.provider_name, rows)
        session.commit()
        _print({"result": "persisted", "provider": res.provider,
                "inserted": res.inserted, "skipped_duplicates": res.skipped_duplicates})
    return 0


def collect_news(args) -> int:
    settings = get_settings()
    asset, asset_id = _require_asset(args.ticker, args.exchange, settings)
    if asset is None:
        return 2
    from app.collectors.exa import ExaNewsCollector
    from app.collectors.exceptions import ProviderError
    from app.services.persist import persist_news
    from app.database.session import get_session_factory

    company = asset.name or args.ticker
    query = args.query or f"{company} {args.ticker} financial news"
    coll = ExaNewsCollector(settings=settings)
    try:
        items = coll.search(query, days=args.days, company_name=company)
    except ProviderError as e:
        print(f"RESULT: provider_error category={e.category} message={e.message!r}")
        return 0
    factory = get_session_factory()
    with factory() as session:
        res = persist_news(session, asset_id, items)
        session.commit()
        _print({"result": "persisted", "provider": res.provider,
                "inserted": res.inserted, "skipped_duplicates": res.skipped_duplicates,
                "synthetic_timestamps": res.synthetic_timestamps})
    return 0


def collect_social(args) -> int:
    settings = get_settings()
    asset, asset_id = _require_asset(args.ticker, args.exchange, settings)
    if asset is None:
        return 2
    from app.collectors.apify import ApifySocialCollector, CANDIDATE_ACTORS
    from app.collectors.exceptions import ProviderError
    from app.services.persist import persist_social
    from app.database.session import get_session_factory

    coll = ApifySocialCollector(settings=settings)
    ref = args.actor or next(c.ref for c in CANDIDATE_ACTORS if c.platform == args.platform)
    avail = coll.verify_actor(ref, platform=args.platform)
    if not avail.available:
        print(f"REFUSED: Actor {ref!r} not usable ({avail.reason}). No run, no replacement.")
        return 2
    # Build a minimal candidate input; validation against the ACTUAL schema is
    # the gate — if the schema does not accept it, the run is not performed.
    run_input = {"keyword": args.ticker, "searchString": args.ticker}
    try:
        run = coll.run_actor(ref, run_input)
        raw = coll.fetch_items(run)
        items = coll.to_social_items(raw, platform=args.platform)
    except ProviderError as e:
        print(f"RESULT: provider_error category={e.category} message={e.message!r}")
        return 0
    factory = get_session_factory()
    with factory() as session:
        res = persist_social(session, asset_id, items)
        session.commit()
        _print({"result": "persisted", "provider": res.provider,
                "inserted": res.inserted, "skipped_duplicates": res.skipped_duplicates,
                "synthetic_timestamps": res.synthetic_timestamps})
    return 0


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    p = argparse.ArgumentParser(description="Phase 5 collection runner")
    p.add_argument("--days", type=int, default=10, help="lookback window in days")
    sub = p.add_subparsers(dest="cmd", required=True)

    pm = sub.add_parser("probe-market")
    pm.add_argument("--ticker", required=True)
    pm.add_argument("--exchange", choices=["HKEX", "KRX", None], default=None)
    pm.set_defaults(func=probe_market)

    pn = sub.add_parser("probe-news")
    pn.add_argument("--query", default=None)
    pn.add_argument("--ticker", default=None)
    pn.add_argument("--domains", default=None, help="comma-separated include_domains")
    pn.set_defaults(func=probe_news)

    va = sub.add_parser("verify-actors")
    va.set_defaults(func=verify_actors)

    cm = sub.add_parser("collect-market")
    cm.add_argument("--ticker", required=True)
    cm.add_argument("--exchange", default=None)
    cm.set_defaults(func=collect_market)

    cn = sub.add_parser("collect-news")
    cn.add_argument("--ticker", required=True)
    cn.add_argument("--exchange", default=None)
    cn.add_argument("--query", default=None)
    cn.set_defaults(func=collect_news)

    cs = sub.add_parser("collect-social")
    cs.add_argument("--ticker", required=True)
    cs.add_argument("--platform", default="telegram",
                    choices=["telegram", "lihkg", "unknown"])
    cs.add_argument("--actor", default=None, help="explicit Actor ref override")
    cs.add_argument("--exchange", default=None)
    cs.set_defaults(func=collect_social)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
