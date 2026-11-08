"""Background worker system (Phase 7).

Job processing using PostgreSQL-based queueing with:
- FOR UPDATE SKIP LOCKED for concurrent-safe claiming
- Advisory locks for scheduler coordination
- Exponential backoff for transient failures
- Reaper for stuck jobs
- Graceful shutdown (SIGTERM/SIGINT)
"""

from app.workers.main import worker_loop, main
from app.workers.claim import claim_next_job, mark_job_done, mark_job_failed, get_worker_id
from app.workers.scheduler import run_scheduler, schedule_daily_collection_jobs
from app.workers.reaper import reap_stuck_jobs
from app.workers.dispatch import dispatch_job

__all__ = [
    "worker_loop",
    "main",
    "claim_next_job",
    "mark_job_done",
    "mark_job_failed",
    "get_worker_id",
    "run_scheduler",
    "schedule_daily_collection_jobs",
    "reap_stuck_jobs",
    "dispatch_job",
]
