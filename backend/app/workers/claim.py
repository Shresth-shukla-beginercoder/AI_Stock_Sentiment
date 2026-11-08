"""Job claiming logic using PostgreSQL FOR UPDATE SKIP LOCKED (Phase 7).

Concurrent-safe job claiming: multiple workers can run simultaneously without
conflict. Each worker claims exactly one job atomically.
"""

from typing import Optional
from datetime import datetime, timezone
import socket

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.database.models import CollectionJob
from app.core.logging import get_logger

_log = get_logger("workers.claim")


def get_worker_id() -> str:
    """Generate worker ID: hostname:pid."""
    return f"{socket.gethostname()}:{os.getpid()}"


def claim_next_job(session: Session, worker_id: str) -> Optional[CollectionJob]:
    """Claim the next available job using FOR UPDATE SKIP LOCKED.

    Atomically:
    1. Find the oldest queued job that is ready to run (run_after <= now or NULL)
    2. Lock it with FOR UPDATE SKIP LOCKED (skip locked rows)
    3. Update status to 'running', set claimed_by and claimed_at
    4. Increment attempts counter

    Returns the claimed job or None if no job is available.
    """
    now = datetime.now(timezone.utc)

    # Find the oldest ready job that is not locked by another worker
    stmt = (
        select(CollectionJob)
        .where(
            and_(
                CollectionJob.status == "queued",
                # Job is ready: run_after is NULL or in the past
                (CollectionJob.run_after.is_(None)) | (CollectionJob.run_after <= now),
            )
        )
        .order_by(CollectionJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )

    result = session.execute(stmt).scalar_one_or_none()

    if result is None:
        return None

    # Claim the job
    result.status = "running"
    result.claimed_by = worker_id
    result.claimed_at = now
    result.attempts += 1
    result.error = None  # Clear previous error

    session.flush()

    _log.info(
        "claimed job",
        extra={
            "job_id": result.id,
            "job_type": result.job_type,
            "dedupe_key": result.dedupe_key,
            "attempts": result.attempts,
            "worker_id": worker_id,
        },
    )

    return result


def mark_job_done(session: Session, job: CollectionJob, counts: Optional[dict] = None) -> None:
    """Mark a job as successfully completed."""
    job.status = "done"
    job.counts = counts
    job.error = None
    session.flush()

    _log.info(
        "job completed",
        extra={
            "job_id": job.id,
            "job_type": job.job_type,
            "dedupe_key": job.dedupe_key,
            "counts": counts,
        },
    )


def mark_job_failed(
    session: Session, job: CollectionJob, error: str, retry_after: Optional[datetime] = None
) -> None:
    """Mark a job as failed.

    If attempts < max_attempts and retry_after is provided, requeue the job.
    Otherwise, mark it as permanently failed.
    """
    job.error = error[:1000]  # Truncate to prevent oversized errors

    if job.attempts < job.max_attempts and retry_after is not None:
        # Retry with exponential backoff
        job.status = "queued"
        job.run_after = retry_after
        job.claimed_by = None
        job.claimed_at = None

        _log.warning(
            "job failed, will retry",
            extra={
                "job_id": job.id,
                "job_type": job.job_type,
                "dedupe_key": job.dedupe_key,
                "attempts": job.attempts,
                "max_attempts": job.max_attempts,
                "retry_after": retry_after.isoformat(),
                "error": error[:200],
            },
        )
    else:
        # Permanent failure
        job.status = "failed"

        _log.error(
            "job permanently failed",
            extra={
                "job_id": job.id,
                "job_type": job.job_type,
                "dedupe_key": job.dedupe_key,
                "attempts": job.attempts,
                "max_attempts": job.max_attempts,
                "error": error[:200],
            },
        )

    session.flush()


import os  # Import at module level
