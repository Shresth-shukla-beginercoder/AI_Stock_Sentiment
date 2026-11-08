"""Worker main loop (Phase 7).

Entry point: python -m app.workers.main [--once]

Graceful shutdown on SIGTERM/SIGINT.
"""

import signal
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.database.session import get_session_factory
from app.workers.claim import claim_next_job, mark_job_done, mark_job_failed, get_worker_id
from app.workers.dispatch import dispatch_job
from app.workers.exceptions import UnsupportedJobError
from app.workers.reaper import reap_stuck_jobs
from app.workers.scheduler import run_scheduler
from app.core.logging import get_logger

_log = get_logger("workers.main")

# Graceful shutdown flag
_shutdown_requested = False


def signal_handler(signum, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    _log.info(f"received {sig_name}, requesting graceful shutdown")
    _shutdown_requested = True


def calculate_retry_after(attempts: int) -> datetime:
    """Calculate exponential backoff: 1, 2, 4, 8, ... minutes."""
    backoff_minutes = 2 ** (attempts - 1)
    return datetime.now(timezone.utc) + timedelta(minutes=backoff_minutes)


def worker_loop(once: bool = False) -> None:
    """Main worker loop.

    If once=True, process one job and exit.
    Otherwise, run continuously until shutdown signal.
    """
    worker_id = get_worker_id()
    _log.info("worker starting", extra={"worker_id": worker_id, "once": once})

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    factory = get_session_factory()
    iteration = 0
    idle_count = 0

    while not _shutdown_requested:
        iteration += 1

        # Every 10 iterations, run scheduler and reaper
        if iteration % 10 == 1:
            try:
                with factory() as session:
                    run_scheduler(session)
            except Exception as e:
                _log.error("scheduler error", extra={"error": str(e)}, exc_info=True)

            try:
                with factory() as session:
                    reaped = reap_stuck_jobs(session)
                    if reaped > 0:
                        _log.info("reaper reaped stuck jobs", extra={"count": reaped})
            except Exception as e:
                _log.error("reaper error", extra={"error": str(e)}, exc_info=True)

        # Claim and process one job
        try:
            with factory() as session:
                job = claim_next_job(session, worker_id)

                if job is None:
                    # No job available
                    session.commit()
                    idle_count += 1

                    if once:
                        _log.info("no jobs available, exiting (--once mode)")
                        break

                    # Sleep with interruption check
                    if idle_count <= 3:
                        time.sleep(1)  # Short sleep for first few idle cycles
                    else:
                        time.sleep(5)  # Longer sleep after sustained idle
                    continue

                # Reset idle counter when we get a job
                idle_count = 0

                # Commit the claim before processing
                session.commit()

                # Process the job
                try:
                    _log.info(
                        "processing job",
                        extra={
                            "job_id": job.id,
                            "job_type": job.job_type,
                            "dedupe_key": job.dedupe_key,
                            "attempts": job.attempts,
                        },
                    )

                    counts = dispatch_job(session, job)
                    mark_job_done(session, job, counts)
                    session.commit()

                    _log.info(
                        "job completed successfully",
                        extra={
                            "job_id": job.id,
                            "job_type": job.job_type,
                            "counts": counts,
                        },
                    )

                except UnsupportedJobError as e:
                    # Permanent failure: unsupported job type (train, unknown, etc.)
                    session.rollback()

                    error_msg = f"{e.reason}: {e.detail}"

                    with factory() as retry_session:
                        # Re-fetch the job in a new session
                        retry_job = retry_session.get(type(job), job.id)
                        if retry_job:
                            # Mark as permanent failure without retry
                            mark_job_failed(retry_session, retry_job, error_msg, None)
                            retry_session.commit()

                    _log.warning(
                        "job permanently failed (unsupported)",
                        extra={
                            "job_id": job.id,
                            "job_type": job.job_type,
                            "reason": e.reason,
                            "error": error_msg[:200],
                        },
                    )

                except Exception as e:
                    # Job failed
                    session.rollback()

                    error_msg = str(e)
                    retry_after = calculate_retry_after(job.attempts)

                    with factory() as retry_session:
                        # Re-fetch the job in a new session
                        retry_job = retry_session.get(type(job), job.id)
                        if retry_job:
                            mark_job_failed(retry_session, retry_job, error_msg, retry_after)
                            retry_session.commit()

                    _log.error(
                        "job failed",
                        extra={
                            "job_id": job.id,
                            "job_type": job.job_type,
                            "error": error_msg[:200],
                        },
                        exc_info=True,
                    )

                if once:
                    _log.info("processed one job, exiting (--once mode)")
                    break

        except Exception as e:
            _log.error("worker loop error", extra={"error": str(e)}, exc_info=True)
            time.sleep(5)  # Back off on unexpected errors

    _log.info("worker shutting down", extra={"worker_id": worker_id})


def main():
    """Entry point for the worker."""
    once = "--once" in sys.argv

    try:
        worker_loop(once=once)
    except KeyboardInterrupt:
        _log.info("worker interrupted by user")
    except Exception as e:
        _log.error("worker fatal error", extra={"error": str(e)}, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
