"""Job scheduler using PostgreSQL advisory locks (Phase 7).

Creates scheduled jobs for data collection and sentiment scoring.
Only one scheduler runs at a time using pg_try_advisory_lock.
"""

from datetime import datetime, timezone, date, timedelta
from typing import List

from sqlalchemy import select, text
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database.models import CollectionJob, Asset
from app.core.logging import get_logger

_log = get_logger("workers.scheduler")

# Advisory lock ID (arbitrary constant)
SCHEDULER_LOCK_ID = 202611081330  # Phase 7 timestamp


def try_acquire_scheduler_lock(session: Session) -> bool:
    """Try to acquire the scheduler advisory lock.

    Returns True if lock was acquired, False if another scheduler holds it.
    """
    result = session.execute(text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": SCHEDULER_LOCK_ID})
    acquired = result.scalar()
    return bool(acquired)


def release_scheduler_lock(session: Session) -> None:
    """Release the scheduler advisory lock."""
    session.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": SCHEDULER_LOCK_ID})


def schedule_daily_collection_jobs(session: Session, target_date: date) -> int:
    """Schedule collection jobs for all confirmed assets for the given date.

    Uses ON CONFLICT DO NOTHING to skip already-scheduled jobs (dedupe_key uniqueness).

    Returns the number of jobs scheduled (inserted).
    """
    # Get all confirmed assets
    stmt = select(Asset).where(Asset.confirmed == True)
    assets = session.execute(stmt).scalars().all()

    if not assets:
        _log.warning("no confirmed assets found, nothing to schedule")
        return 0

    jobs_to_schedule = []
    for asset in assets:
        # Job 1: Collect market prices
        jobs_to_schedule.append({
            "dedupe_key": f"collect:market:{asset.ticker}:{target_date}",
            "job_type": "collect:market",
            "status": "queued",
            "params": {
                "asset_id": asset.id,
                "ticker": asset.ticker,
                "exchange": asset.exchange,
                "target_date": target_date.isoformat(),
            },
            "run_after": None,  # Run immediately
            "attempts": 0,
            "max_attempts": 3,
        })

        # Job 2: Collect social posts
        jobs_to_schedule.append({
            "dedupe_key": f"collect:social:{asset.ticker}:{target_date}",
            "job_type": "collect:social",
            "status": "queued",
            "params": {
                "asset_id": asset.id,
                "ticker": asset.ticker,
                "exchange": asset.exchange,
                "target_date": target_date.isoformat(),
            },
            "run_after": None,
            "attempts": 0,
            "max_attempts": 3,
        })

        # Job 3: Collect news articles
        jobs_to_schedule.append({
            "dedupe_key": f"collect:news:{asset.ticker}:{target_date}",
            "job_type": "collect:news",
            "status": "queued",
            "params": {
                "asset_id": asset.id,
                "ticker": asset.ticker,
                "exchange": asset.exchange,
                "target_date": target_date.isoformat(),
            },
            "run_after": None,
            "attempts": 0,
            "max_attempts": 3,
        })

        # Job 4: Score sentiment (runs after collection)
        # Delay sentiment scoring by 30 minutes to allow collection to complete
        run_after = datetime.now(timezone.utc) + timedelta(minutes=30)
        jobs_to_schedule.append({
            "dedupe_key": f"score:sentiment:{asset.ticker}:{target_date}",
            "job_type": "score:sentiment",
            "status": "queued",
            "params": {
                "asset_id": asset.id,
                "ticker": asset.ticker,
                "session_date": target_date.isoformat(),
            },
            "run_after": run_after,
            "attempts": 0,
            "max_attempts": 3,
        })

    # Bulk insert with ON CONFLICT DO NOTHING
    if jobs_to_schedule:
        stmt = pg_insert(CollectionJob).values(jobs_to_schedule).on_conflict_do_nothing(
            constraint="uq_collection_jobs_dedupe_key"
        )
        result = session.execute(stmt)
        session.commit()

        # Note: rowcount is unreliable with ON CONFLICT DO NOTHING on PostgreSQL
        # We log the total scheduled count, not the actual inserted count
        _log.info(
            "scheduled daily jobs",
            extra={
                "target_date": target_date.isoformat(),
                "assets": len(assets),
                "jobs_scheduled": len(jobs_to_schedule),
            },
        )

    return len(jobs_to_schedule)


def run_scheduler(session: Session) -> bool:
    """Run the scheduler: acquire lock, schedule jobs, release lock.

    Returns True if scheduler ran, False if another scheduler was already running.
    """
    if not try_acquire_scheduler_lock(session):
        _log.debug("scheduler lock held by another instance, skipping")
        return False

    try:
        _log.info("scheduler acquired lock, running")

        # Schedule jobs for today
        today = date.today()
        count = schedule_daily_collection_jobs(session, today)

        _log.info("scheduler run complete", extra={"jobs_scheduled": count})
        return True
    finally:
        release_scheduler_lock(session)
