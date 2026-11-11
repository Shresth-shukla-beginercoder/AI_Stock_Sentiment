"""Job dispatcher: routes jobs to appropriate handlers (Phase 7).

Handlers connect to Phase 5 collectors and Phase 6 sentiment pipeline.
"""

from typing import Optional, Dict, Any
from datetime import datetime, date, timezone

from sqlalchemy import select, and_, func
from sqlalchemy.orm import Session

from app.database.models import CollectionJob
from app.core.logging import get_logger
from app.core.config import get_settings
from app.workers.exceptions import UnsupportedJobError

_log = get_logger("workers.dispatch")


def handle_collect_market(session: Session, job: CollectionJob) -> Dict[str, Any]:
    """Handle collect:market job - fetch daily prices via the provider chain.

    Phase 14: the owner-selected primary provider (Twelve Data) runs first; a
    keyless yfinance fallback is tried when the primary errors or returns no
    bars (HKEX plan-gate 404 / KRX 429). Rows are persisted under the
    provider that actually produced them, preserving per-row attribution.
    """
    from app.collectors.chain import market_provider_chain, fetch_daily_prices
    from app.services.persist import resolve_asset, persist_market_prices

    settings = get_settings()
    params = job.params or {}
    ticker = params.get("ticker")
    if not ticker:
        raise ValueError("collect:market requires params['ticker']")
    target_date = date.fromisoformat(params["target_date"])

    # Fetch price data for the target date.
    # For daily data, fetch a small window around the target date.
    start_date = target_date
    end_date = target_date
    exchange = params.get("exchange")

    _log.info("collecting market data",
              extra={"ticker": ticker, "date": target_date.isoformat()})

    chain = market_provider_chain(settings, ticker, start_date, end_date, exchange=exchange)
    provider, rows, attempts = fetch_daily_prices(chain)

    asset = resolve_asset(session, ticker, exchange)
    if asset is None:
        # Honest: never fabricate an asset. Log and report zero counts.
        _log.warning("collect:market: asset not resolved; skipping persistence",
                     extra={"ticker": ticker})
        return {
            "provider": provider.provider_name,
            "fetched": len(rows),
            "inserted": 0,
            "skipped_duplicates": 0,
            "asset_resolved": False,
            "chain": attempts,
        }

    result = persist_market_prices(session, asset.id, provider.provider_name, rows)
    session.commit()

    return {
        "provider": provider.provider_name,
        "fetched": len(rows),
        "inserted": result.inserted,
        "skipped_duplicates": result.skipped_duplicates,
        "asset_resolved": True,
        "chain": attempts,
    }


def handle_backfill_market(session: Session, job: CollectionJob) -> Dict[str, Any]:
    """Handle a backfill:market job - fetch + persist ONE chunk of history.

    Phase A1: the historical window is pre-chunked at enqueue time (one job per
    chunk, dedupe_key ``backfill:market:{ticker}:{start}:{end}``), so this
    handler fetches a single chunk - sized to stay under the provider's
    per-call bar cap - and persists it under the provider that actually
    produced the rows (primary Twelve Data, else yfinance fallback).

    The chunk fetch is wrapped in ``bounded_retry`` so a yfinance rate limit
    (429) or transport fault retries with backoff rather than failing the job.
    Persistence is ``ON CONFLICT DO NOTHING`` on (asset_id, trade_date,
    provider), so re-running a chunk never duplicates or overwrites existing
    bars. Regular daily ``collect:market`` behaviour is untouched.
    """
    from app.collectors.chain import market_provider_chain, fetch_daily_prices
    from app.collectors.retry import bounded_retry
    from app.services.persist import resolve_asset, persist_market_prices

    settings = get_settings()
    params = job.params or {}
    ticker = params.get("ticker")
    start_iso = params.get("start")
    end_iso = params.get("end")
    if not (ticker and start_iso and end_iso):
        raise ValueError(
            "backfill:market requires params['ticker'], params['start'] and params['end']"
        )

    start = date.fromisoformat(start_iso)
    end = date.fromisoformat(end_iso)
    exchange = params.get("exchange")

    _log.info("backfilling market chunk",
              extra={"ticker": ticker, "start": start_iso, "end": end_iso})

    chain = market_provider_chain(settings, ticker, start, end, exchange=exchange)

    def _fetch():
        return fetch_daily_prices(chain)

    provider, rows, attempts = bounded_retry(_fetch, settings=settings)

    asset = resolve_asset(session, ticker, exchange)
    if asset is None:
        _log.warning("backfill:market: asset not resolved; skipping persistence",
                     extra={"ticker": ticker})
        return {
            "provider": provider.provider_name,
            "fetched": len(rows),
            "inserted": 0,
            "skipped_duplicates": 0,
            "asset_resolved": False,
            "window": [start_iso, end_iso],
            "chain": attempts,
        }

    result = persist_market_prices(session, asset.id, provider.provider_name, rows)
    session.commit()

    return {
        "provider": provider.provider_name,
        "fetched": len(rows),
        "inserted": result.inserted,
        "skipped_duplicates": result.skipped_duplicates,
        "asset_resolved": True,
        "window": [start_iso, end_iso],
        "chain": attempts,
    }


def handle_collect_social(session: Session, job: CollectionJob) -> Dict[str, Any]:
    """Handle collect:social job — run the exchange's configured Apify Actors.

    W1: execution is CONFIG-DRIVEN (``settings.apify_actor_*``), never the old
    hard-coded candidate list. Per configured platform the worker:

    1. verifies the actor exists and is accessible for this account;
    2. builds the run input from the actor's OWN example/schema (never guessed
       fields — an input that cannot be built safely is recorded and skipped);
    3. runs the actor with bounded wait, item cap and charge cap
       (``apify_run_wait_seconds`` / ``apify_run_max_items`` /
       ``apify_run_max_charge_usd``);
    4. maps the dataset output to normalized posts and persists them
       (ON CONFLICT DO NOTHING dedupe; engagement NULL when unknown).

    Unconfigured platforms (e.g. KRX kakao/naver) are recorded as
    ``not configured`` — never filled with an invented actor. Transient
    failures on every attempted run raise so the worker retries with backoff;
    per-actor outcomes are always included in the job counts.
    """
    from app.collectors.apify import ApifySocialCollector, resolve_exchange_actors
    from app.collectors.exceptions import TransientError, RateLimitError
    from app.services.persist import resolve_asset, persist_social

    settings = get_settings()
    params = job.params or {}
    ticker = params.get("ticker")
    if not ticker:
        raise ValueError("collect:social requires params['ticker']")
    target_date = date.fromisoformat(params["target_date"])
    exchange = params.get("exchange")

    _log.info("collecting social posts",
              extra={"ticker": ticker, "date": target_date.isoformat(), "exchange": exchange})

    asset = resolve_asset(session, ticker, exchange)
    if asset is None:
        _log.warning("collect:social: asset not resolved; skipping", extra={"ticker": ticker})
    collector = ApifySocialCollector(settings=settings,
                                     run_wait_seconds=settings.apify_run_wait_seconds)
    records = resolve_exchange_actors(settings, exchange, collector, ticker)

    fetched = 0
    inserted = 0
    skipped = 0
    attempted = 0
    hard_failures = 0
    for rec in records:
        if not rec["configured"] or not rec["available"] or rec["run_input"] is None:
            continue
        if asset is None:
            rec["note"] = "asset not resolved; fetched data is NOT persisted"
            continue
        attempted += 1
        try:
            run = collector.run_actor(
                rec["actor"],
                rec["run_input"],
                wait=None,  # uses run_wait_seconds from settings
                max_items=settings.apify_run_max_items,
                max_total_charge_usd=settings.apify_run_max_charge_usd,
            )
        except (TransientError, RateLimitError) as e:
            hard_failures += 1
            rec["note"] = f"run failed ({type(e).__name__}): {e}"
            _log.warning("social actor run failed",
                         extra={"actor": rec["actor"], "platform": rec["platform"],
                                "error": str(e)[:200]})
            continue
        except Exception as e:  # provider/other hard error
            hard_failures += 1
            rec["note"] = f"run failed ({type(e).__name__}): {e}"
            _log.warning("social actor run failed (unexpected)",
                         extra={"actor": rec["actor"], "platform": rec["platform"],
                                "error": str(e)[:200]})
            continue
        raw = collector.fetch_items(run)
        items = collector.to_social_items(raw, platform=rec["platform"])
        rec["fetched"] = len(raw)
        rec["mapped"] = len(items)
        if items:
            res = persist_social(session, asset.id, items)
            inserted += res.inserted
            skipped += res.skipped_duplicates
            fetched += len(items)
            rec["inserted"] = res.inserted
            rec["skipped_duplicates"] = res.skipped_duplicates
        else:
            rec["note"] = "run completed, 0 usable posts (empty dataset or unmappable items)"

    if asset is not None:
        session.commit()

    if hard_failures and hard_failures == attempted:
        # Every attempted actor run failed -> let the worker retry the job.
        raise TransientError(
            f"all {attempted} attempted social actor run(s) failed; "
            f"outcomes: {[r.get('note') or r['reason'] for r in records if r.get('note')]}"
        )

    return {
        "provider": "apify",
        "exchange": exchange,
        "fetched": fetched,
        "inserted": inserted,
        "skipped_duplicates": skipped,
        "asset_resolved": asset is not None,
        "actors": records,
    }


def handle_collect_news(session: Session, job: CollectionJob) -> Dict[str, Any]:
    """Handle collect:news job - fetch news articles via Exa."""
    from app.collectors.exa import ExaNewsCollector
    from app.services.persist import resolve_asset, persist_news

    settings = get_settings()
    params = job.params or {}
    ticker = params.get("ticker")
    if not ticker:
        raise ValueError("collect:news requires params['ticker']")
    ticker_name = params.get("ticker_name") or ticker
    target_date = date.fromisoformat(params["target_date"])

    _log.info("collecting news articles", extra={"ticker": ticker, "date": target_date.isoformat()})

    collector = ExaNewsCollector(settings=settings)
    query = f"{ticker_name} {ticker} news"
    items = collector.search(query, end=target_date)

    asset = resolve_asset(session, ticker, params.get("exchange"))
    if asset is None:
        _log.warning("collect:news: asset not resolved; skipping persistence",
                     extra={"ticker": ticker})
        return {
            "provider": "exa",
            "fetched": len(items),
            "inserted": 0,
            "skipped_duplicates": 0,
            "asset_resolved": False,
        }

    # W3: drop articles that do not mention the asset (name / ticker /
    # provider ticker). Metadata and publication timestamps are preserved on
    # every item that is kept.
    from app.collectors.relevance import filter_asset_relevant
    kept, rel = filter_asset_relevant(
        items,
        name=asset.name,
        ticker=ticker,
        provider_ticker=asset.provider_ticker,
    )

    result = persist_news(session, asset.id, kept)
    session.commit()

    return {
        "provider": "exa",
        "fetched": len(items),
        "relevance": {
            "relevant": rel.relevant,
            "ambiguous_kept": rel.ambiguous,
            "irrelevant_dropped": rel.irrelevant_dropped,
            "no_ticker_kept": rel.no_ticker_kept,
        },
        "inserted": result.inserted,
        "skipped_duplicates": result.skipped_duplicates,
        "null_published_at": result.null_published_at,
        "asset_resolved": True,
    }


def handle_score_sentiment(session: Session, job: CollectionJob) -> Dict[str, Any]:
    """Handle score:sentiment job - analyze sentiment for collected posts/articles.

    Uses Phase 6 pipeline (preprocess -> language routing -> model select ->
    analyze -> persist). Posts/articles that already have a result for the
    routed model are skipped via the unique (item_type, item_id, model_name)
    constraint so the job is idempotent.
    """
    from app.sentiment import (
        preprocess_for_sentiment,
        detect_language,
        select_model,
        analyze,
        persist_sentiment_result,
    )
    from app.database.models import SocialPost, NewsArticle, Asset
    from app.features.sessions import session_utc_range

    params = job.params or {}
    asset_id = params.get("asset_id")
    ticker = params.get("ticker")
    session_date = date.fromisoformat(params["session_date"])

    # W2: the session date is an EXCHANGE-LOCAL day. Resolve the asset's
    # exchange and filter by the UTC half-open range that covers it
    # (HK = UTC+8, KR = UTC+9), not by a raw UTC calendar date.
    asset = session.get(Asset, asset_id) if asset_id else None
    exchange = params.get("exchange") or (asset.exchange if asset else None)
    win_start, win_end = session_utc_range(session_date, exchange)

    _log.info("scoring sentiment",
              extra={"ticker": ticker, "date": session_date.isoformat(),
                     "exchange": exchange,
                     "session_utc_range": [win_start.isoformat(), win_end.isoformat()]})

    ts_social = func.coalesce(SocialPost.published_at, SocialPost.created_at)
    ts_news = func.coalesce(NewsArticle.published_at, NewsArticle.created_at)

    # Fetch social posts for this asset's session (published_at, else created_at).
    social_posts = session.execute(
        select(SocialPost).where(
            and_(
                SocialPost.asset_id == asset_id,
                ts_social >= win_start,
                ts_social < win_end,
            )
        )
    ).scalars().all()

    # Fetch news articles for the same session.
    news_articles = session.execute(
        select(NewsArticle).where(
            and_(
                NewsArticle.asset_id == asset_id,
                ts_news >= win_start,
                ts_news < win_end,
            )
        )
    ).scalars().all()

    social_scored = 0
    news_scored = 0
    social_skipped = 0
    news_skipped = 0

    for post in social_posts:
        text = preprocess_for_sentiment(post.content)
        if not text:
            social_skipped += 1
            continue

        lang = detect_language(text)
        model_id = select_model(text, "social")
        if not model_id:
            # Language has no verified model (e.g. CJK) -> skip honestly.
            social_skipped += 1
            continue

        score = analyze(text, model_id)
        if score is None:
            social_skipped += 1
            continue

        persist_result = persist_sentiment_result(
            session,
            "social_post",
            post.id,
            score.model_id,
            score.label,
            score.score,
            score.p_pos,
            score.p_neu,
            score.p_neg,
        )
        if persist_result.inserted > 0:
            social_scored += 1

    for article in news_articles:
        text = preprocess_for_sentiment(article.body or article.title)
        if not text:
            news_skipped += 1
            continue

        model_id = select_model(text, "news")
        if not model_id:
            news_skipped += 1
            continue

        score = analyze(text, model_id)
        if score is None:
            news_skipped += 1
            continue

        persist_result = persist_sentiment_result(
            session,
            "news_article",
            article.id,
            score.model_id,
            score.label,
            score.score,
            score.p_pos,
            score.p_neu,
            score.p_neg,
        )
        if persist_result.inserted > 0:
            news_scored += 1

    session.commit()

    return {
        "social_posts_scored": social_scored,
        "social_posts_skipped": social_skipped,
        "news_articles_scored": news_scored,
        "news_articles_skipped": news_skipped,
        "total_scored": social_scored + news_scored,
    }


# W6: real "train" handler — previously unsupported (worker marked train jobs
# as permanent failures). Trains per ticker, registers the model version, and
# persists the next-TRADING-session prediction.
def handle_train(session: Session, job: CollectionJob) -> Dict[str, Any]:
    """Handle a train job: per-ticker walk-forward + holdout + OOS reporting.

    params: {"tickers": [...]} (empty/None = all confirmed+active assets),
            optional "model_name" (default "wf-ridge").

    Per ticker:
      - build features from stored prices + sentiment (live rows only);
      - walk-forward CV + strict chronological holdout (settings.ml_random_seed
        / settings.ml_holdout_ratio), with no-change & always-up baselines;
      - register the model version (skipped honestly if already registered);
      - persist the next-TRADING-session prediction (target date = the next
        observed bar's date, price basis = that row's CLOSE, never a return).

    OOS honesty: the registry entry carries the holdout metrics; if the model
    does not beat the no-change baseline, that is recorded, not hidden.
    """
    from datetime import datetime
    from app.database.models import Asset
    from app.features.build_features import build_features, filter_for_training
    from app.models.trainer import train_and_evaluate, predict_next_session
    from app.models.registry import register_model, persist_predictions, get_model
    from app.features.make_target import predicted_price as _pp

    def _git_commit() -> str:
        # Real commit for the model registry when running inside a git worktree;
        # otherwise an honest placeholder. Never invent a SHA.
        import subprocess
        try:
            out = subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
            )
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.strip()
        except Exception:
            pass
        return "no_git_repo"

    settings = get_settings()
    params = job.params or {}
    tickers = params.get("tickers") or []
    model_name = params.get("model_name") or "wf-ridge"

    q = select(Asset).where(Asset.confirmed == True, Asset.active == True)  # noqa: E712
    assets = list(session.execute(q).scalars().all())
    if tickers:
        wanted = set(tickers)
        assets = [a for a in assets
                  if a.ticker in wanted or (a.provider_ticker and a.provider_ticker in wanted)]

    results: list[Dict[str, Any]] = []
    for asset in assets:
        entry: Dict[str, Any] = {"ticker": asset.ticker, "model_name": model_name}
        try:
            rows = build_features(session, asset.id, lookback_days=90)
            trainable = filter_for_training(rows, require_target=True)
            if len(trainable) < 10:
                entry["status"] = "insufficient_history"
                entry["rows"] = len(trainable)
                results.append(entry)
                continue

            stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d")
            version = f"{model_name}-{stamp}-{asset.ticker}"
            if get_model(session, version) is not None:
                entry["status"] = "version_already_registered"
                entry["model_version"] = version
                results.append(entry)
                continue

            registry_entry = train_and_evaluate(
                trainable,
                model_version=version,
                git_commit=_git_commit(),
                seed=settings.ml_random_seed,
                holdout_ratio=settings.ml_holdout_ratio,
            )
            register_model(
                session,
                model_version=registry_entry["model_version"],
                mae=registry_entry.get("mae"),
                rmse=registry_entry.get("rmse"),
                directional_accuracy=registry_entry.get("directional_accuracy"),
                baseline_nochange_mae=registry_entry.get("baseline_nochange_mae"),
                baseline_nochange_rmse=registry_entry.get("baseline_nochange_rmse"),
                baseline_nochange_dir_acc=registry_entry.get("baseline_nochange_dir_acc"),
                baseline_alwaysup_dir_acc=registry_entry.get("baseline_alwaysup_dir_acc"),
                n_test=registry_entry.get("n_test"),
                params=registry_entry.get("params"),
                git_commit=registry_entry.get("git_commit"),
                force=False,
            )
            entry.update({
                "status": "trained",
                "model_version": version,
                "oos_mae": registry_entry.get("oos_mae"),
                "oos_nochange_mae": registry_entry.get("oos_nochange_mae"),
                "beats_nochange_baseline": registry_entry.get("beats_nochange_baseline"),
                "experimental": registry_entry.get("experimental"),
            })

            # Next-trading-session prediction from the LAST row only.
            pred = predict_next_session(
                trainable,
                seed=settings.ml_random_seed,
            )
            if pred is None or pred["target_date"] is None:
                entry["prediction"] = "skipped (no target session resolvable)"
            else:
                # Sanity: price basis must be the row's CLOSE, never a return.
                assert pred["predicted_price"] is None or _pp(
                    pred["basis_close"], pred["predicted_return"]
                ) == pred["predicted_price"]
                persisted = persist_predictions(
                    session,
                    asset.id,
                    version,
                    [{
                        "target_date": pred["target_date"],
                        "predicted_return": pred["predicted_return"],
                        "predicted_price": pred["predicted_price"],
                        "actual_close": None,  # backfilled later (W6)
                        "experimental": pred["experimental"] or registry_entry.get("experimental", True),
                    }],
                )
                entry["prediction"] = {
                    "target_date": pred["target_date"].isoformat(),
                    "predicted_return": pred["predicted_return"],
                    "predicted_price": pred["predicted_price"],
                    "persisted": persisted,
                }
        except Exception as e:
            entry["status"] = f"failed: {type(e).__name__}: {e}"
        results.append(entry)

    session.commit()
    _log.info("train job complete", extra={"tickers": len(results)})
    return {"trained": [r for r in results if r.get("status") == "trained"],
            "results": results}


# Dispatcher registry
HANDLERS = {
    "collect:market": handle_collect_market,
    "backfill:market": handle_backfill_market,
    "collect:social": handle_collect_social,
    "collect:news": handle_collect_news,
    "score:sentiment": handle_score_sentiment,
    "train": handle_train,
}


def dispatch_job(session: Session, job: CollectionJob) -> Dict[str, Any]:
    """Dispatch a job to its handler.

    Returns a counts dictionary on success.
    Raises an exception on failure (caller handles retry logic).

    Unsupported types (train, unknown) raise :class:`UnsupportedJobError`;
    the worker marks them as permanent failures without retry.
    """
    handler = HANDLERS.get(job.job_type)

    if handler is None:
        raise UnsupportedJobError(
            job.job_type,
            "unknown_job_type",
            f"No handler registered for job type: {job.job_type}",
        )

    _log.debug("dispatching job", extra={"job_id": job.id, "job_type": job.job_type})

    return handler(session, job)
