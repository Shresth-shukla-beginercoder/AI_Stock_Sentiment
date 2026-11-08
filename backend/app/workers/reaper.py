"""Reaper: detect and recover stuck running jobs (Phase 7).

Jobs that have been running for too long (> threshold) are considered stuck
and requeued or marked failed.
"""

from datetime import datetime, timezone, timedelta

from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from app.database.models import CollectionJob
from app.core.logging import get_logger

_log = get_logger("workers.reaper")

# Job is stuck if running for more than this duration
STUCK_JOB_THRESHOLD = timedelta(minutes=30)


def reap_stuck_jobs(session: Session) -> int:
    """Find jobs that have been running too long and requeue or fail them.

    Returns the number of reaped jobs.
    """
    now = datetime.now(timezone.utc)
    stuck_threshold = now - STUCK_JOB_THRESHOLD

    # Find running jobs that were claimed before the threshold
    stmt = select(CollectionJob).where(
        and_(
            CollectionJob.status == "running",
            CollectionJob.claimed_at.is_not(None),
            CollectionJob.claimed_at < stuck_threshold,
        )
    )

    stuck_jobs = session.execute(stmt).scalars().all()

    if not stuck_jobs:
        return 0

    count = 0
    for job in stuck_jobs:
        error_msg = f"Job stuck (running > {STUCK_JOB_THRESHOLD.total_seconds()}s). Worker {job.claimed_by} may have crashed."

        if job.attempts < job.max_attempts:
            # Requeue with exponential backoff
            backoff_minutes = 2 ** (job.attempts - 1)  # 1, 2, 4, ...
            retry_after = now + timedelta(minutes=backoff_minutes)

            job.status = "queued"
            job.run_after = retry_after
            job.claimed_by = None
            job.claimed_at = None
            job.error = error_msg

            _log.warning(
                "reaped stuck job, will retry",
                extra={
                    "job_id": job.id,
                    "job_type": job.job_type,
                    "dedupe_key": job.dedupe_key,
                    "attempts": job.attempts,
                    "retry_after": retry_after.isoformat(),
                    "stuck_since": job.claimed_at.isoformat() if job.claimed_at else None,
                },
            )
        else:
            # Permanent failure
            job.status = "failed"
            job.error = error_msg

            _log.error(
                "reaped stuck job, permanently failed",
                extra={
                    "job_id": job.id,
                    "job_type": job.job_type,
                    "dedupe_key": job.dedupe_key,
                    "attempts": job.attempts,
                    "stuck_since": job.claimed_at.isoformat() if job.claimed_at else None,
                },
            )

        count += 1

    session.commit()

    _log.info("reaper run complete", extra={"reaped": count})
    return count
