"""Phase 3 API contract: all business routes under /api.

Design rules:
- Branch on the explicit DATA_MODE setting: "demo" -> deterministic synthetic
  in-memory data; "live" -> database reads with honest no_data states.
- Demo and live rows are NEVER combined in one response.
- Every data response carries data_mode + as_of (UTC ISO-8601).
- Later-phase capabilities return structured unavailable/planned status,
  never fake work. POSTs create real collection_jobs rows (202 only then).
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.core.config import get_settings
from app.database.session import get_session, session_scope
from app.schemas.api import CollectRunRequest, TrainRequest
from app.schemas.envelope import APIError, ok, paginated_meta
from app.services import demo_data, report, store

router = APIRouter()

_DEMO_SOURCE = "demo-synthetic"
_DB_SOURCE = "database"
_PHASE_NOTES = {
    "posts": "Social collection (Phase 5, Apify); rows stay empty until a verified actor run persists posts for the asset.",
    "news": "News collection (Phase 5, Exa); rows stay empty until a fetch persists articles for the asset.",
    "prices": "Market data (Phase 5, Twelve Data + fallback); live HKEX/KRX fetch is pending asset approval and provider capability.",
    "sentiment": "Sentiment scoring (Phase 6); results appear once collection + score:sentiment jobs have run.",
    "predictions": "Predictions (Phase 8); rows appear once a train job has run.",
    "models": "Model registry (Phase 8); rows appear once a train job has run.",
}

# POST /collect/run fans out to per-ticker jobs of these handler-served types
# (W7: the API must only queue job types the worker actually executes).
_SOURCE_JOB_TYPES = {"social": "collect:social", "news": "collect:news"}


def _demo_universe_note() -> str:
    return (
        "Synthetic demo universe (is_demo=true). Not real market data. "
        "The 10 proposed HKEX/KRX tickers remain PENDING CONFIRMATION."
    )


def _require_demo_ticker(ticker: str) -> None:
    if ticker not in demo_data.DEMO_TICKERS:
        raise APIError(
            404,
            "not_found",
            f"Unknown demo ticker '{ticker}'. Demo universe: {list(demo_data.DEMO_TICKERS)}.",
        )


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------
@router.get("/system/status")
def system_status() -> dict:
    """System status: data mode, provider name, credentials presence, feature status."""
    settings = get_settings()
    return {
        "success": True,
        "data": {
            "app": "ai-stock-backend",
            "version": "1.0.0",
            "data_mode": settings.data_mode,
            "market_data_provider": settings.market_data_provider or None,
            "provider_capability": (
                "UNVERIFIED for HKEX/KRX asset coverage: Twelve Data auth + response "
                "schema verified in Phase 5 (US symbols fetch OHLCV), but HKEX is "
                "plan-gated and KRX resolution was rate-limited on the current tier. "
                "Collectors are implemented; live HKEX/KRX fetch is pending asset "
                "approval."
            ),
            "credentials": {
                "configured": settings.configured_credentials(),
                "missing": settings.missing_credentials(),
            },
            "feature_status": {
                "demo_data": "available",
                "collectors": "implemented (Phase 5): twelve_data / exa / apify clients + normalisation + idempotent persistence",
                "market_data_provider": settings.market_data_provider or "none-configured",
                "sentiment": "implemented (Phase 6): per-item scoring + session aggregation; results appear once collection jobs have run",
                "worker": "implemented (Phase 7): persistent relational-DB job queue (claim / reaper / scheduler); runs as its own service",
                "model_training": "implemented (Phase 8): walk-forward + OOS holdout registry; versions appear once a train job has run",
            },
        },
        "meta": {"source": "config"},
        "data_mode": settings.data_mode,
        "as_of": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# Assets
# ---------------------------------------------------------------------------
@router.get("/assets")
def list_assets(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    settings = get_settings()
    if settings.data_mode == "demo":
        rows = demo_data.list_assets()
        total = len(rows)
        page = rows[offset : offset + limit]
        return ok(
            page,
            meta=paginated_meta(limit=limit, offset=offset, total=total, state="ok", source=_DEMO_SOURCE, note=_demo_universe_note()),
            data_mode="demo",
        )
    with session_scope() as session:
        rows = store.list_assets(session)
        total = len(rows)
        page = rows[offset : offset + limit]
        return ok(
            page,
            meta=paginated_meta(
                limit=limit,
                offset=offset,
                total=total,
                state="ok" if total else "no_data",
                source=_DB_SOURCE,
                note="No assets seeded yet — the 10 proposed tickers remain pending owner confirmation.",
            ),
            data_mode="live",
        )


@router.get("/assets/{ticker}")
def get_asset(
    ticker: str,
    session: Session = Depends(get_session),
) -> dict:
    settings = get_settings()
    if settings.data_mode == "demo":
        _require_demo_ticker(ticker)
        asset = demo_data.get_asset(ticker)
        return ok(asset, meta={"source": _DEMO_SOURCE, "note": _demo_universe_note()}, data_mode="demo")
    asset = store.asset_or_none(session, ticker)
    if asset is None:
        raise APIError(404, "not_found", f"Unknown ticker '{ticker}' in live asset store.")
    return ok(store.asset_dict(asset), meta={"source": _DB_SOURCE}, data_mode="live")


# ---------------------------------------------------------------------------
# Social posts
# ---------------------------------------------------------------------------
@router.get("/posts/{ticker}")
def get_posts(
    ticker: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    settings = get_settings()
    if settings.data_mode == "demo":
        _require_demo_ticker(ticker)
        rows = demo_data.get_posts(ticker)
        total = len(rows)
        page = rows[offset : offset + limit]
        return ok(
            page,
            meta=paginated_meta(limit=limit, offset=offset, total=total, state="ok", source=_DEMO_SOURCE, note=_demo_universe_note()),
            data_mode="demo",
        )
    with session_scope() as session:
        rows, total = store.list_posts(session, ticker, limit, offset)
        return ok(
            rows,
            meta=paginated_meta(limit=limit, offset=offset, total=total, state="ok" if total else "no_data", source=_DB_SOURCE, note=_PHASE_NOTES["posts"]),
            data_mode="live",
        )


# ---------------------------------------------------------------------------
# Sentiment
# ---------------------------------------------------------------------------
@router.get("/sentiment/{ticker}")
def get_sentiment(ticker: str) -> dict:
    settings = get_settings()
    if settings.data_mode == "demo":
        _require_demo_ticker(ticker)
        return ok(demo_data.get_sentiment(ticker), meta={"source": _DEMO_SOURCE, "note": _demo_universe_note()}, data_mode="demo")
    with session_scope() as session:
        return ok(store.sentiment_for_ticker(session, ticker), meta={"source": _DB_SOURCE, "note": _PHASE_NOTES["sentiment"]}, data_mode="live")


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------
@router.get("/news/{ticker}")
def get_news(
    ticker: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    settings = get_settings()
    if settings.data_mode == "demo":
        _require_demo_ticker(ticker)
        rows = demo_data.get_news(ticker)
        total = len(rows)
        page = rows[offset : offset + limit]
        return ok(
            page,
            meta=paginated_meta(limit=limit, offset=offset, total=total, state="ok", source=_DEMO_SOURCE, note=_demo_universe_note()),
            data_mode="demo",
        )
    with session_scope() as session:
        rows, total = store.list_news(session, ticker, limit, offset)
        return ok(
            rows,
            meta=paginated_meta(limit=limit, offset=offset, total=total, state="ok" if total else "no_data", source=_DB_SOURCE, note=_PHASE_NOTES["news"]),
            data_mode="live",
        )


# ---------------------------------------------------------------------------
# Market prices
# ---------------------------------------------------------------------------
@router.get("/prices/{ticker}")
def get_prices(
    ticker: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    settings = get_settings()
    if settings.data_mode == "demo":
        _require_demo_ticker(ticker)
        rows = demo_data.get_prices(ticker)
        total = len(rows)
        page = rows[offset : offset + limit]
        return ok(
            page,
            meta=paginated_meta(limit=limit, offset=offset, total=total, state="ok", source=_DEMO_SOURCE, note=_demo_universe_note()),
            data_mode="demo",
        )
    with session_scope() as session:
        rows, total = store.list_prices(session, ticker, limit, offset)
        return ok(
            rows,
            meta=paginated_meta(limit=limit, offset=offset, total=total, state="ok" if total else "no_data", source=_DB_SOURCE, note=_PHASE_NOTES["prices"]),
            data_mode="live",
        )


# ---------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------
@router.get("/predictions/{ticker}")
def get_predictions(
    ticker: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    settings = get_settings()
    if settings.data_mode == "demo":
        _require_demo_ticker(ticker)
        rows = demo_data.get_predictions(ticker)
        total = len(rows)
        page = rows[offset : offset + limit]
        return ok(
            page,
            meta=paginated_meta(limit=limit, offset=offset, total=total, state="ok", source=_DEMO_SOURCE, note="Experimental demo predictions — not financial advice."),
            data_mode="demo",
        )
    with session_scope() as session:
        rows, total = store.list_predictions(session, ticker, limit, offset)
        return ok(
            rows,
            meta=paginated_meta(limit=limit, offset=offset, total=total, state="ok" if total else "no_data", source=_DB_SOURCE, note=_PHASE_NOTES["predictions"]),
            data_mode="live",
        )


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
@router.get("/reports/overview")
def reports_overview() -> dict:
    settings = get_settings()
    if settings.data_mode == "demo":
        return ok(demo_data.get_overview(), meta={"source": _DEMO_SOURCE, "note": _demo_universe_note()}, data_mode="demo")
    with session_scope() as session:
        data = store.overview(session)
        return ok(data, meta={"source": _DB_SOURCE, "note": _PHASE_NOTES["models"]}, data_mode="live")


@router.get("/reports/ranking")
def reports_ranking() -> dict:
    settings = get_settings()
    if settings.data_mode == "demo":
        return ok(demo_data.get_ranking(), meta={"source": _DEMO_SOURCE, "note": _demo_universe_note()}, data_mode="demo")
    with session_scope() as session:
        data = store.ranking(session)
        return ok(data, meta={"source": _DB_SOURCE, "note": _PHASE_NOTES["sentiment"]}, data_mode="live")


@router.get("/reports/tickers")
def reports_tickers() -> dict:
    """W5: per-ticker, exchange-separated report (price / sentiment / direction
    / S-R / mentions). Demo and live return the SAME shape."""
    settings = get_settings()
    if settings.data_mode == "demo":
        return ok(demo_data.get_ticker_report(), meta={"source": _DEMO_SOURCE, "note": _demo_universe_note()}, data_mode="demo")
    with session_scope() as session:
        data = report.build_ticker_report(session)
        return ok(data, meta={"source": _DB_SOURCE, "note": "Per-ticker report over stored data; nulls mark missing data, never zero."}, data_mode="live")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
@router.get("/models/evaluation")
def models_evaluation(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    settings = get_settings()
    if settings.data_mode == "demo":
        rows = demo_data.get_evaluations()
        total = len(rows)
        page = rows[offset : offset + limit]
        return ok(
            page,
            meta=paginated_meta(limit=limit, offset=offset, total=total, state="ok", source=_DEMO_SOURCE, note="Synthetic demo metrics — not from a real training run."),
            data_mode="demo",
        )
    with session_scope() as session:
        rows, total = store.list_evaluations(session, limit, offset)
        return ok(
            rows,
            meta=paginated_meta(limit=limit, offset=offset, total=total, state="ok" if total else "no_data", source=_DB_SOURCE, note=_PHASE_NOTES["models"]),
            data_mode="live",
        )


@router.get("/models/versions")
def models_versions() -> dict:
    settings = get_settings()
    if settings.data_mode == "demo":
        rows = demo_data.get_evaluations()
        versions = [r["model_version"] for r in rows]
        return ok(
            {"versions": versions},
            meta={"source": _DEMO_SOURCE, "note": "Synthetic demo model versions."},
            data_mode="demo",
        )
    with session_scope() as session:
        versions = store.model_versions(session)
        return ok(
            {"versions": versions},
            meta={"source": _DB_SOURCE, "note": "Empty until Phase 8 training runs persist versions."},
            data_mode="live",
        )


# ---------------------------------------------------------------------------
# Jobs (admin)
# ---------------------------------------------------------------------------
@router.get("/jobs", dependencies=[Depends(require_admin)])
def list_jobs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> dict:
    rows, total = store.list_jobs(session, limit, offset)
    return ok(
        rows,
        meta=paginated_meta(limit=limit, offset=offset, total=total, state="ok" if total else "no_data", source=_DB_SOURCE, note="Executed by the running worker service (Phase 7 dispatch)."),
        data_mode=get_settings().data_mode,
    )


@router.get("/jobs/{job_id}", dependencies=[Depends(require_admin)])
def get_job(job_id: int, session: Session = Depends(get_session)) -> dict:
    job = store.job_or_none(session, job_id)
    if job is None:
        raise APIError(404, "not_found", f"Unknown job id {job_id}.")
    return ok(job, meta={"source": _DB_SOURCE}, data_mode=get_settings().data_mode)


# ---------------------------------------------------------------------------
# Collection & training (admin, persistent queue)
# ---------------------------------------------------------------------------
@router.post("/collect/run", status_code=202, dependencies=[Depends(require_admin)])
def collect_run(body: CollectRunRequest, session: Session = Depends(get_session)) -> dict:
    """Persist real collection jobs the worker can execute.

    W7: the queue contains per-ticker ``collect:social`` / ``collect:news``
    rows (the job types the worker's dispatch actually serves) — never the
    un-servable legacy ``collect`` type. 202 when at least one row is
    inserted; 409 when every requested job is already queued.
    """
    settings = get_settings()
    target_date = store.today_utc().isoformat()
    sources = ["social", "news"] if body.source == "all" else [body.source]
    jobs: list[dict[str, Any]] = []
    duplicate_ids: list[int] = []
    for ticker in sorted(body.tickers):
        for src in sources:
            job_type = _SOURCE_JOB_TYPES[src]
            dedupe_key = f"{job_type}:{ticker}:{target_date}:{body.label or '-'}"
            params = {"ticker": ticker, "target_date": target_date, "label": body.label}
            job, created = store.queue_job(
                session, job_type=job_type, dedupe_key=dedupe_key, params=params
            )
            jobs.append({
                "ticker": ticker,
                "source": src,
                "job_type": job_type,
                "job_id": job.id,
                "status": job.status,
                "created": created,
            })
            if not created:
                duplicate_ids.append(job.id)
    if not any(j["created"] for j in jobs):
        raise APIError(
            409,
            "duplicate_job",
            "All requested collection jobs are already queued.",
            {"jobs": jobs},
        )
    return ok(
        {"target_date": target_date, "jobs": jobs, "duplicate_job_ids": duplicate_ids},
        meta={
            "source": _DB_SOURCE,
            "note": "Per-ticker jobs queued; each is executed by the running worker (Phase 7 dispatch).",
        },
        data_mode=settings.data_mode,
    )


@router.post("/models/train", status_code=202, dependencies=[Depends(require_admin)])
def models_train(body: TrainRequest, session: Session = Depends(get_session)) -> dict:
    """Persist a real training job. 202 when a row is actually inserted; 409 on duplicate."""
    tickers = ",".join(sorted(body.tickers)) if body.tickers else "*"
    dedupe_key = f"train:{body.model_name or 'auto'}:{tickers}"
    params = {"tickers": body.tickers, "model_name": body.model_name}
    job, created = store.queue_job(session, job_type="train", dedupe_key=dedupe_key, params=params)
    if not created:
        raise APIError(
            409,
            "duplicate_job",
            "An identical training job is already queued.",
            {"job_id": job.id, "dedupe_key": job.dedupe_key, "status": job.status},
        )
    return ok(
        {"job_id": job.id, "dedupe_key": job.dedupe_key, "status": job.status, "params": job.params},
        meta={"source": _DB_SOURCE, "note": "Job queued; executed by the worker's train handler (Phase 8 walk-forward + OOS holdout)."},
        data_mode=get_settings().data_mode,
    )
