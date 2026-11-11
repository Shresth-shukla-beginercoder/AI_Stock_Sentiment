"""Manual / CLI collection runner for Phase 5.

Phase 5 is *reusable provider clients + collector services + controlled
manual execution* — not a background worker (that is Phase 7). This script is
how a human (or the Phase 7 worker, later) drives a bounded collection run.

Subcommands
-----------
probe-market     Fetch + normalize prices, print a summary. NO persistence.
probe-news       Run one news search, print a summary. NO persistence.
verify-actors    Check each CONFIGURED Apify Actor (settings refs, per
                 exchange) exists / is accessible, and report the actual
                 input schema / example. NO run, no cost.
collect-market   Fetch + persist prices for an *approved* asset (gated).
collect-news     Search + persist news for an asset (gated on a real asset row).
collect-social   Run + persist a verified, CONFIGURED Actor for an asset. The
                 run input is built from the Actor's own schema/example
                 (never guessed); the run is bounded + cost-capped.
backfill-market  Enqueue historical market-price backfill jobs (enqueue-only).
                 The background worker does the actual fetch + persist. Use
                 --dry-run to preview the plan without touching the queue.
backfill-predictions
                   Fill NULL actual_close values on prediction rows from
                   stored market-price bars (W6). Only NULLs are touched.

The collect-* paths refuse to touch data for tickers that have no ``assets``
row (or that are not confirmed), because the 10 proposed tickers are PENDING
the user's explicit confirmation. Probes are read-only and never persist.

Run from the ``backend/`` directory::

    python -m app.scripts.collect probe-market --ticker 0700 --exchange HKEX --days 5
    python -m app.scripts.collect backfill-market --dry-run --lookback-days 183
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


def _db_persist_guard(subcommand: str) -> None:
    """W7: persisting subcommands must never silently write to a remote DB.

    The repo-root .env may set ``DATABASE_URL`` to the production (Neon)
    instance; the script's ``load_dotenv`` puts it into the process env, and
    settings resolve it with priority over the local dev parts. Guard: if the
    resolved host is not a known local one, refuse unless the operator
    explicitly opted in via ``COLLECT_ALLOW_NONLOCAL_DB=1``. The value of the
    URL (credentials included) is never printed — only the host.
    """
    from urllib.parse import urlparse

    settings = get_settings()
    host = urlparse(settings.database_url_resolved()).hostname or "unknown"
    local = host in {"localhost", "127.0.0.1", "postgres", "host.docker.internal"}
    if not local and os.environ.get("COLLECT_ALLOW_NONLOCAL_DB") != "1":
        raise SystemExit(
            f"REFUSED: '{subcommand}' would persist to a NON-LOCAL database "
            f"(host={host!r}). Local smoke runs must use the dev DB. "
            f"To target the resolved remote DB deliberately, set "
            f"COLLECT_ALLOW_NONLOCAL_DB=1 in the process environment."
        )
    print(f"DB: '{subcommand}' will persist to host={host!r} "
          f"({'local' if local else 'NON-LOCAL — operator override active'})")


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
    """W1: verify the CONFIGURED Actor refs for an exchange (settings-driven).

    Read-only and cost-free: no Actor run, no social data. Reports the actual
    input schema / example the Actor exposes so inputs are built from the
    Actor's own contract, never guessed. Unconfigured platforms are recorded
    honestly — no Actor id is invented.
    """
    from app.collectors.apify import (
        ApifySocialCollector,
        build_run_input,
        configured_actors,
    )
    from app.collectors.exceptions import ProviderError

    settings = get_settings()
    coll = ApifySocialCollector(settings=settings)
    exchanges = ["HKEX", "KRX"] if args.exchange == "ALL" else [args.exchange]
    any_configured = False
    for ex in exchanges:
        for platform, ref in configured_actors(settings, ex):
            record = {"exchange": ex, "platform": platform, "actor": ref or None,
                     "configured": bool(ref)}
            if not ref:
                record["available"] = False
                record["reason"] = ("not configured — set the matching settings field "
                                    "(apify_actor_<platform>) to an owner-chosen ref")
                _print(record)
                continue
            any_configured = True
            try:
                avail = coll.verify_actor(ref, platform=platform)
                record["available"] = avail.available
                record["reason"] = avail.reason
                record["is_public"] = avail.is_public
                record["is_deprecated"] = avail.is_deprecated
                record["has_input_schema"] = avail.input_schema is not None
                record["has_example_input"] = isinstance(avail.example_input, dict)
                record["example_input"] = avail.example_input
                if avail.available and args.ticker:
                    inp, note = build_run_input(avail, args.ticker)
                    record["run_input_constructible"] = inp is not None
                    record["input_note"] = note
                    if args.dump_schema and avail.input_schema is not None:
                        record["input_schema"] = avail.input_schema
            except ProviderError as e:
                record["available"] = False
                record["reason"] = f"{e.category}: {e.message}"
            _print(record)
    if not any_configured:
        print("NOTE: no configured Actor refs for the requested exchange(s) — "
              "nothing was verified and nothing was run.")
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
    _db_persist_guard("collect-market")
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
    _db_persist_guard("collect-news")
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
                "null_published_at": res.null_published_at})
    return 0


def collect_social(args) -> int:
    """W1: run + persist a CONFIGURED, verified Actor for an asset (gated).

    The Actor ref comes from settings (per exchange), never from the
    hard-coded candidate list. The run input is built from the Actor's own
    input schema / example (``build_run_input``) — never guessed — and the run
    is bounded by item + charge caps (settings defaults, overridable via flags
    for a controlled smoke run). Unconfigured platforms are refused honestly.
    """
    settings = get_settings()
    _db_persist_guard("collect-social")
    asset, asset_id = _require_asset(args.ticker, args.exchange, settings)
    if asset is None:
        return 2
    from app.collectors.apify import (
        ApifySocialCollector,
        build_run_input,
        configured_actors,
    )
    from app.collectors.exceptions import ProviderError
    from app.services.persist import persist_social
    from app.database.session import get_session_factory

    exchange = args.exchange or asset.exchange
    platform_map = dict(configured_actors(settings, exchange))
    if args.platform in platform_map and platform_map[args.platform]:
        ref = args.actor or platform_map[args.platform]
        platform = args.platform
    elif args.platform == "auto":
        for p, r in configured_actors(settings, exchange):
            if r:
                ref, platform = (args.actor or r), p
                break
        else:
            ref, platform = None, None
    else:
        # Explicit platform but not configured for this exchange.
        ref, platform = (args.actor or platform_map.get(args.platform) or None), args.platform

    if not ref:
        print(f"REFUSED: no configured Actor ref for platform {platform!r} on exchange "
              f"{exchange!r}. Set apify_actor_{platform} in settings/.env — "
              f"no Actor id will be invented.")
        return 2

    coll = ApifySocialCollector(settings=settings)
    avail = coll.verify_actor(ref, platform=platform)
    if not avail.available:
        print(f"REFUSED: Actor {ref!r} not usable ({avail.reason}). No run, no replacement.")
        return 2
    run_input, input_note = build_run_input(avail, args.ticker)
    if run_input is None:
        print(f"REFUSED: {input_note}. Run not performed — inputs are never guessed.")
        return 2

    # Bounded, cost-capped run. Defaults from settings; smoke flags can tighten.
    max_items = args.max_items if args.max_items is not None else settings.apify_run_max_items
    max_charge = args.max_charge if args.max_charge is not None else settings.apify_run_max_charge_usd
    wait_s = settings.apify_run_wait_seconds
    try:
        from datetime import timedelta as _td
        run = coll.run_actor(ref, run_input, wait=_td(seconds=wait_s),
                             max_items=max_items, max_total_charge_usd=max_charge)
        raw = coll.fetch_items(run, limit=max_items)
        items = coll.to_social_items(raw, platform=platform)
    except ProviderError as e:
        print(f"RESULT: provider_error category={e.category} message={e.message!r}")
        return 0
    factory = get_session_factory()
    with factory() as session:
        res = persist_social(session, asset_id, items)
        session.commit()
        _print({"result": "persisted", "provider": res.provider,
                "actor": ref, "platform": platform,
                "input_note": input_note,
                "inserted": res.inserted, "skipped_duplicates": res.skipped_duplicates,
                "null_published_at": res.null_published_at})
    return 0


def backfill_market(args) -> int:
    """Enqueue historical market-price backfill jobs (enqueue-only).

    Splits the lookback window into calendar chunks (each under the provider's
    per-call bar cap) and enqueues one ``backfill:market`` job per
    (confirmed asset, chunk) via ON CONFLICT DO NOTHING, so re-running is
    idempotent. The background worker performs the actual fetch + persist.
    ``--dry-run`` prints the plan and touches nothing (read-only).
    """
    from sqlalchemy import select, update, func
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.database.models import CollectionJob, Asset
    from app.database.session import get_session_factory
    from app.collectors.chunking import iter_chunk_windows

    settings = get_settings()
    days = args.lookback_days if args.lookback_days is not None else settings.backfill_default_days
    chunk_days = args.chunk_days if args.chunk_days is not None else settings.backfill_chunk_trading_days

    end = date.today()
    start = end - timedelta(days=days)
    chunk_ranges = iter_chunk_windows(start, end, chunk_days)

    factory = get_session_factory()
    with factory() as session:
        q = (select(Asset)
             .where(Asset.confirmed == True, Asset.active == True)  # noqa: E712
             .order_by(Asset.exchange, Asset.ticker))
        assets = list(session.execute(q).scalars().all())
        if args.assets and args.assets.strip().lower() != "all":
            wanted = {t.strip() for t in args.assets.split(",") if t.strip()}
            assets = [a for a in assets
                      if a.ticker in wanted or (a.provider_ticker and a.provider_ticker in wanted)]

        jobs = []
        for a in assets:
            for cs, ce in chunk_ranges:
                jobs.append({
                    "dedupe_key": f"backfill:market:{a.ticker}:{cs.isoformat()}:{ce.isoformat()}",
                    "job_type": "backfill:market",
                    "status": "queued",
                    "params": {
                        "asset_id": a.id,
                        "ticker": a.ticker,
                        "exchange": a.exchange,
                        "start": cs.isoformat(),
                        "end": ce.isoformat(),
                    },
                    "run_after": None,
                    "attempts": 0,
                    "max_attempts": 3,
                })

        if args.dry_run:
            _print({
                "mode": "dry-run",
                "window": [start.isoformat(), end.isoformat()],
                "lookback_days": days,
                "chunk_trading_days": chunk_days,
                "chunks": [(cs.isoformat(), ce.isoformat()) for cs, ce in chunk_ranges],
                "assets": [a.ticker for a in assets],
                "planned_jobs": len(jobs),
                "dedupe_keys": [j["dedupe_key"] for j in jobs],
            })
            print("NOTE: dry-run — no jobs enqueued, nothing persisted, no worker triggered.")
            return 0

        _db_persist_guard("backfill-market")
        if not jobs:
            print("NOTE: no confirmed+active assets matched; nothing enqueued.")
            return 0

        keys = [j["dedupe_key"] for j in jobs]
        # Enqueue idempotently: existing chunk keys are skipped, not duplicated.
        session.execute(
            pg_insert(CollectionJob).values(jobs)
            .on_conflict_do_nothing(constraint="uq_collection_jobs_dedupe_key")
        )
        # Give any previously-FAILED chunk another chance (fresh retry budget).
        reset = session.execute(
            update(CollectionJob)
            .where(
                CollectionJob.job_type == "backfill:market",
                CollectionJob.status == "failed",
                CollectionJob.dedupe_key.in_(keys),
            )
            .values(status="queued", attempts=0, error=None,
                    claimed_by=None, claimed_at=None, run_after=None,
                    updated_at=func.now())
        )
        session.commit()

        _print({
            "mode": "enqueued",
            "window": [start.isoformat(), end.isoformat()],
            "planned_jobs": len(jobs),
            "reset_failed_jobs": reset.rowcount,
            "dedupe_keys": keys,
        })
        print("NOTE: jobs enqueued. The background worker fetches + persists on its next "
              "run; re-running this command is idempotent (ON CONFLICT DO NOTHING).")
        return 0


def backfill_predictions(args) -> int:
    """W6: fill NULL prediction actual_close values from stored price bars.

    Idempotent and honest: only ``actual_close IS NULL`` rows whose target
    session has already traded are updated (from the asset's configured
    provider when present, else the newest stored bar). Due sessions with no
    stored close stay NULL — never guessed. This writes to the configured
    database, so run it deliberately.
    """
    from app.database.session import get_session_factory
    from app.services.predict_backfill import backfill_actual_closes

    _db_persist_guard("backfill-predictions")
    factory = get_session_factory()
    with factory() as session:
        res = backfill_actual_closes(session, model_version=args.model_version)
        session.commit()
    _print({
        "result": "backfill-predictions",
        "model_version": args.model_version or "(all)",
        "considered": res.considered,
        "updated": res.updated,
        "no_price_yet": res.no_price_yet,
        "future": res.future,
    })
    print("NOTE: only NULL actual_close rows were touched; due sessions without a "
          "stored close stay NULL (never guessed).")
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

    va = sub.add_parser(
        "verify-actors",
        help="verify the CONFIGURED Actor refs for an exchange (read-only, no cost)",
    )
    va.add_argument("--exchange", default="ALL", choices=["HKEX", "KRX", "ALL"])
    va.add_argument("--ticker", default=None,
                    help="report run-input constructibility for this ticker")
    va.add_argument("--dump-schema", action="store_true",
                    help="include the observed input schema in the output")
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
    cs.add_argument("--platform", default="auto",
                    choices=["auto", "telegram", "lihkg", "kakao", "naver"],
                    help="'auto' = first configured platform for the exchange")
    cs.add_argument("--actor", default=None, help="explicit Actor ref override")
    cs.add_argument("--exchange", default=None)
    cs.add_argument("--max-items", type=int, default=None,
                   help="dataset items read (default: settings.apify_run_max_items)")
    cs.add_argument("--max-charge", type=float, default=None,
                   help="per-run USD charge cap (default: settings.apify_run_max_charge_usd)")
    cs.set_defaults(func=collect_social)

    bf = sub.add_parser(
        "backfill-market",
        help="enqueue historical market-price backfill jobs (enqueue-only; "
             "--dry-run previews without touching the queue)",
    )
    bf.add_argument("--lookback-days", type=int, default=None,
                   help="calendar lookback window in days (default: settings.backfill_default_days)")
    bf.add_argument("--assets", default="all",
                   help="'all' confirmed+active assets, or a comma list of tickers")
    bf.add_argument("--chunk-days", type=int, default=None,
                   help="max trading days per chunk (default: settings.backfill_chunk_trading_days)")
    bf.add_argument("--dry-run", action="store_true",
                    help="print the planned jobs; enqueue nothing, persist nothing")
    bf.set_defaults(func=backfill_market)

    bpr = sub.add_parser(
        "backfill-predictions",
        help="fill NULL prediction actual_close values from stored price bars "
             "(W6; writes to the configured DB)",
    )
    bpr.add_argument("--model-version", default=None,
                     help="restrict to one model version (default: all)")
    bpr.set_defaults(func=backfill_predictions)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
