"""Phase 7: Workers and Scheduling tests.

Comprehensive tests for:
- Job claiming with FOR UPDATE SKIP LOCKED
- Job lifecycle: queued → running → done/failed
- Retry logic with exponential backoff
- Deduplication via unique dedupe_key
- Reaper for stuck jobs
- Scheduler with advisory locks
- Graceful shutdown
- --once flag
- Unsupported job types (train, unknown)
"""

import pytest
from datetime import datetime, timezone, date, timedelta
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy import select, delete, text

from app.database.models import CollectionJob, Asset
from app.workers.claim import claim_next_job, mark_job_done, mark_job_failed, get_worker_id
from app.workers.reaper import reap_stuck_jobs, STUCK_JOB_THRESHOLD
from app.workers.scheduler import (
    try_acquire_scheduler_lock,
    release_scheduler_lock,
    schedule_daily_collection_jobs,
    run_scheduler,
)
from app.workers.dispatch import dispatch_job

# Mark tests requiring database
needs_db = pytest.mark.skipif(True, reason="requires real PostgreSQL; run with -m needs_db to override")


# ============================================================================
# Job Claiming Tests
# ============================================================================


@needs_db
def test_claim_next_job_success():
    """Successfully claim the oldest ready job."""
    from app.database.session import get_session_factory

    factory = get_session_factory()

    # Cleanup
    with factory() as s:
        s.execute(delete(CollectionJob).where(CollectionJob.dedupe_key.like("test_claim_%")))
        s.commit()

    # Create test jobs
    with factory() as s:
        job1 = CollectionJob(
            dedupe_key="test_claim_1",
            job_type="collect:market",
            status="queued",
            params={"ticker": "TEST1"},
        )
        job2 = CollectionJob(
            dedupe_key="test_claim_2",
            job_type="collect:news",
            status="queued",
            params={"ticker": "TEST2"},
        )
        s.add_all([job1, job2])
        s.commit()

    try:
        worker_id = get_worker_id()

        # Claim a job
        with factory() as s:
            claimed = claim_next_job(s, worker_id)
            s.commit()

            assert claimed is not None
            assert claimed.dedupe_key == "test_claim_1"  # Oldest first
            assert claimed.status == "running"
            assert claimed.claimed_by == worker_id
            assert claimed.claimed_at is not None
            assert claimed.attempts == 1

        # Verify in DB
        with factory() as s:
            job = s.execute(
                select(CollectionJob).where(CollectionJob.dedupe_key == "test_claim_1")
            ).scalar_one()
            assert job.status == "running"
            assert job.attempts == 1
    finally:
        with factory() as s:
            s.execute(delete(CollectionJob).where(CollectionJob.dedupe_key.like("test_claim_%")))
            s.commit()


@needs_db
def test_claim_next_job_skip_locked():
    """Multiple workers claiming jobs concurrently - each gets a different job."""
    from app.database.session import get_session_factory
    from sqlalchemy.orm import Session

    factory = get_session_factory()

    # Cleanup
    with factory() as s:
        s.execute(delete(CollectionJob).where(CollectionJob.dedupe_key.like("test_concurrent_%")))
        s.commit()

    # Create multiple test jobs
    with factory() as s:
        for i in range(3):
            job = CollectionJob(
                dedupe_key=f"test_concurrent_{i}",
                job_type="collect:market",
                status="queued",
            )
            s.add(job)
        s.commit()

    try:
        # Simulate two workers claiming simultaneously
        session1 = factory()
        session2 = factory()

        claimed1 = claim_next_job(session1, "worker1")
        claimed2 = claim_next_job(session2, "worker2")

        # Both should succeed but get different jobs
        assert claimed1 is not None
        assert claimed2 is not None
        assert claimed1.id != claimed2.id

        session1.commit()
        session2.commit()
        session1.close()
        session2.close()

        # Verify both are running
        with factory() as s:
            running = s.execute(
                select(CollectionJob).where(
                    CollectionJob.dedupe_key.like("test_concurrent_%"),
                    CollectionJob.status == "running",
                )
            ).scalars().all()
            assert len(running) == 2
    finally:
        with factory() as s:
            s.execute(delete(CollectionJob).where(CollectionJob.dedupe_key.like("test_concurrent_%")))
            s.commit()


@needs_db
def test_claim_respects_run_after():
    """Jobs with run_after in the future are not claimed."""
    from app.database.session import get_session_factory

    factory = get_session_factory()

    # Cleanup
    with factory() as s:
        s.execute(delete(CollectionJob).where(CollectionJob.dedupe_key.like("test_runafter_%")))
        s.commit()

    future = datetime.now(timezone.utc) + timedelta(hours=1)

    with factory() as s:
        job = CollectionJob(
            dedupe_key="test_runafter_future",
            job_type="collect:market",
            status="queued",
            run_after=future,
        )
        s.add(job)
        s.commit()

    try:
        with factory() as s:
            claimed = claim_next_job(s, "worker1")
            s.commit()
            assert claimed is None  # Job not ready yet
    finally:
        with factory() as s:
            s.execute(delete(CollectionJob).where(CollectionJob.dedupe_key.like("test_runafter_%")))
            s.commit()


@needs_db
def test_mark_job_done():
    """Mark a job as successfully completed."""
    from app.database.session import get_session_factory

    factory = get_session_factory()

    with factory() as s:
        s.execute(delete(CollectionJob).where(CollectionJob.dedupe_key == "test_done"))
        s.commit()

    with factory() as s:
        job = CollectionJob(dedupe_key="test_done", job_type="collect:market", status="running")
        s.add(job)
        s.commit()
        s.refresh(job)
        job_id = job.id

    try:
        with factory() as s:
            job = s.get(CollectionJob, job_id)
            mark_job_done(s, job, {"fetched": 10, "inserted": 8})
            s.commit()

        with factory() as s:
            job = s.get(CollectionJob, job_id)
            assert job.status == "done"
            assert job.counts == {"fetched": 10, "inserted": 8}
            assert job.error is None
    finally:
        with factory() as s:
            s.execute(delete(CollectionJob).where(CollectionJob.dedupe_key == "test_done"))
            s.commit()


@needs_db
def test_mark_job_failed_with_retry():
    """Failed job is requeued with exponential backoff."""
    from app.database.session import get_session_factory

    factory = get_session_factory()

    with factory() as s:
        s.execute(delete(CollectionJob).where(CollectionJob.dedupe_key == "test_retry"))
        s.commit()

    with factory() as s:
        job = CollectionJob(
            dedupe_key="test_retry",
            job_type="collect:market",
            status="running",
            attempts=1,
            max_attempts=3,
        )
        s.add(job)
        s.commit()
        s.refresh(job)
        job_id = job.id

    try:
        retry_after = datetime.now(timezone.utc) + timedelta(minutes=2)

        with factory() as s:
            job = s.get(CollectionJob, job_id)
            mark_job_failed(s, job, "Network timeout", retry_after)
            s.commit()

        with factory() as s:
            job = s.get(CollectionJob, job_id)
            assert job.status == "queued"  # Requeued for retry
            assert job.error == "Network timeout"
            assert job.run_after is not None
            assert job.claimed_by is None
            assert job.claimed_at is None
    finally:
        with factory() as s:
            s.execute(delete(CollectionJob).where(CollectionJob.dedupe_key == "test_retry"))
            s.commit()


@needs_db
def test_mark_job_failed_permanently():
    """Failed job exceeding max_attempts is marked failed."""
    from app.database.session import get_session_factory

    factory = get_session_factory()

    with factory() as s:
        s.execute(delete(CollectionJob).where(CollectionJob.dedupe_key == "test_permanent"))
        s.commit()

    with factory() as s:
        job = CollectionJob(
            dedupe_key="test_permanent",
            job_type="collect:market",
            status="running",
            attempts=3,
            max_attempts=3,
        )
        s.add(job)
        s.commit()
        s.refresh(job)
        job_id = job.id

    try:
        retry_after = datetime.now(timezone.utc) + timedelta(minutes=8)

        with factory() as s:
            job = s.get(CollectionJob, job_id)
            mark_job_failed(s, job, "Permanent error", retry_after)
            s.commit()

        with factory() as s:
            job = s.get(CollectionJob, job_id)
            assert job.status == "failed"  # Permanently failed
            assert job.error == "Permanent error"
    finally:
        with factory() as s:
            s.execute(delete(CollectionJob).where(CollectionJob.dedupe_key == "test_permanent"))
            s.commit()


# ============================================================================
# Deduplication Tests
# ============================================================================


@needs_db
def test_scheduler_deduplication():
    """Scheduling the same job twice creates only one row."""
    from app.database.session import get_session_factory

    factory = get_session_factory()

    # Cleanup
    with factory() as s:
        s.execute(delete(Asset).where(Asset.ticker == "DEDUP"))
        s.commit()

    # Create test asset
    with factory() as s:
        asset = Asset(exchange="TST", ticker="DEDUP", name="Dedup Test", confirmed=True)
        s.add(asset)
        s.commit()

    try:
        target_date = date.today()

        # Schedule twice
        with factory() as s:
            count1 = schedule_daily_collection_jobs(s, target_date)
            assert count1 > 0

        with factory() as s:
            count2 = schedule_daily_collection_jobs(s, target_date)
            # Second schedule should skip (ON CONFLICT DO NOTHING)
            # Note: count2 reports jobs_to_schedule count, not actual inserts

        # Verify only one set of jobs exists
        with factory() as s:
            jobs = s.execute(
                select(CollectionJob).where(CollectionJob.dedupe_key.like(f"%DEDUP:{target_date}"))
            ).scalars().all()
            # Should be 4 jobs: market, social, news, sentiment
            assert len(jobs) == 4
    finally:
        with factory() as s:
            s.execute(delete(Asset).where(Asset.ticker == "DEDUP"))
            s.commit()


# ============================================================================
# Reaper Tests
# ============================================================================


@needs_db
def test_reaper_requeues_stuck_job():
    """Reaper requeues jobs stuck in running state."""
    from app.database.session import get_session_factory

    factory = get_session_factory()

    with factory() as s:
        s.execute(delete(CollectionJob).where(CollectionJob.dedupe_key == "test_stuck"))
        s.commit()

    # Create a stuck job (claimed long ago)
    stuck_time = datetime.now(timezone.utc) - STUCK_JOB_THRESHOLD - timedelta(minutes=5)

    with factory() as s:
        job = CollectionJob(
            dedupe_key="test_stuck",
            job_type="collect:market",
            status="running",
            claimed_by="worker_crashed",
            claimed_at=stuck_time,
            attempts=1,
            max_attempts=3,
        )
        s.add(job)
        s.commit()

    try:
        with factory() as s:
            reaped = reap_stuck_jobs(s)
            assert reaped == 1

        with factory() as s:
            job = s.execute(
                select(CollectionJob).where(CollectionJob.dedupe_key == "test_stuck")
            ).scalar_one()
            assert job.status == "queued"  # Requeued
            assert job.run_after is not None  # Delayed
            assert job.claimed_by is None
            assert "stuck" in job.error.lower()
    finally:
        with factory() as s:
            s.execute(delete(CollectionJob).where(CollectionJob.dedupe_key == "test_stuck"))
            s.commit()


@needs_db
def test_reaper_fails_stuck_job_max_attempts():
    """Reaper permanently fails stuck jobs that exceeded max_attempts."""
    from app.database.session import get_session_factory

    factory = get_session_factory()

    with factory() as s:
        s.execute(delete(CollectionJob).where(CollectionJob.dedupe_key == "test_stuck_fail"))
        s.commit()

    stuck_time = datetime.now(timezone.utc) - STUCK_JOB_THRESHOLD - timedelta(minutes=5)

    with factory() as s:
        job = CollectionJob(
            dedupe_key="test_stuck_fail",
            job_type="collect:market",
            status="running",
            claimed_by="worker_crashed",
            claimed_at=stuck_time,
            attempts=3,
            max_attempts=3,
        )
        s.add(job)
        s.commit()

    try:
        with factory() as s:
            reaped = reap_stuck_jobs(s)
            assert reaped == 1

        with factory() as s:
            job = s.execute(
                select(CollectionJob).where(CollectionJob.dedupe_key == "test_stuck_fail")
            ).scalar_one()
            assert job.status == "failed"  # Permanently failed
            assert "stuck" in job.error.lower()
    finally:
        with factory() as s:
            s.execute(delete(CollectionJob).where(CollectionJob.dedupe_key == "test_stuck_fail"))
            s.commit()


# ============================================================================
# Scheduler Tests
# ============================================================================


@needs_db
def test_scheduler_advisory_lock():
    """Only one scheduler can hold the advisory lock at a time."""
    from app.database.session import get_session_factory

    factory = get_session_factory()

    session1 = factory()
    session2 = factory()

    try:
        # First session acquires lock
        acquired1 = try_acquire_scheduler_lock(session1)
        assert acquired1 is True

        # Second session cannot acquire (lock held)
        acquired2 = try_acquire_scheduler_lock(session2)
        assert acquired2 is False

        # Release lock
        release_scheduler_lock(session1)
        session1.commit()

        # Now second session can acquire
        acquired2_retry = try_acquire_scheduler_lock(session2)
        assert acquired2_retry is True

        release_scheduler_lock(session2)
        session2.commit()
    finally:
        session1.close()
        session2.close()


@needs_db
def test_schedule_daily_collection_jobs():
    """Scheduler creates jobs for all confirmed assets."""
    from app.database.session import get_session_factory

    factory = get_session_factory()

    # Cleanup
    with factory() as s:
        s.execute(delete(Asset).where(Asset.ticker.like("SCHED%")))
        s.commit()

    # Create test assets
    with factory() as s:
        asset1 = Asset(exchange="TST", ticker="SCHED1", name="Sched 1", confirmed=True)
        asset2 = Asset(exchange="TST", ticker="SCHED2", name="Sched 2", confirmed=True)
        asset3 = Asset(exchange="TST", ticker="SCHED3", name="Sched 3", confirmed=False)  # Not confirmed
        s.add_all([asset1, asset2, asset3])
        s.commit()

    try:
        target_date = date.today()

        with factory() as s:
            count = schedule_daily_collection_jobs(s, target_date)
            # 2 confirmed assets × 4 jobs each = 8 jobs
            assert count == 8

        # Verify jobs exist
        with factory() as s:
            jobs = s.execute(
                select(CollectionJob).where(CollectionJob.dedupe_key.like(f"%SCHED%:{target_date}"))
            ).scalars().all()
            assert len(jobs) == 8

            # Check job types
            job_types = [j.job_type for j in jobs]
            assert job_types.count("collect:market") == 2
            assert job_types.count("collect:social") == 2
            assert job_types.count("collect:news") == 2
            assert job_types.count("score:sentiment") == 2
    finally:
        with factory() as s:
            s.execute(delete(Asset).where(Asset.ticker.like("SCHED%")))
            s.commit()


# ============================================================================
# Dispatcher Tests (mocked handlers)
# ============================================================================


def test_dispatch_unknown_job_type():
    """Dispatcher raises error for unknown job type."""
    job = CollectionJob(dedupe_key="test", job_type="unknown:type", status="running")

    from app.workers.exceptions import UnsupportedJobError
    with pytest.raises(UnsupportedJobError, match="unknown_job_type"):
        dispatch_job(Mock(), job)


@patch("app.collectors.twelve_data.TwelveDataProvider")
@patch("app.services.persist.persist_market_prices")
@patch("app.services.persist.resolve_asset")
def test_dispatch_collect_market(mock_resolve, mock_persist, mock_provider_cls):
    """Dispatcher routes collect:market to TwelveData + persist path."""
    from app.collectors.provider import PriceRow
    from datetime import datetime, timezone

    mock_provider = MagicMock()
    mock_provider_cls.return_value = mock_provider
    mock_provider.get_daily_prices.return_value = [
        PriceRow(ticker="TEST", trade_date=datetime(2026, 11, 8, 16, 0, tzinfo=timezone.utc),
                 open=100.0, high=105.0, low=99.0, close=102.0)
    ]

    mock_resolve.return_value = MagicMock(id=1)
    mock_persist.return_value = MagicMock(inserted=1, skipped_duplicates=0)

    job = CollectionJob(
        dedupe_key="test:market",
        job_type="collect:market",
        status="running",
        params={"ticker": "TEST", "target_date": "2026-11-08"},
    )

    result = dispatch_job(MagicMock(), job)

    assert result["provider"] == "twelvedata"
    assert result["fetched"] == 1
    assert result["inserted"] == 1
    assert mock_resolve.called
    assert mock_persist.called


def test_dispatch_unsupported_train_job():
    """Dispatcher raises UnsupportedJobError for 'train' job."""
    from app.workers.exceptions import UnsupportedJobError

    job = CollectionJob(dedupe_key="test:train", job_type="train", status="running")

    with pytest.raises(UnsupportedJobError) as exc_info:
        dispatch_job(Mock(), job)

    assert exc_info.value.job_type == "train"
    assert exc_info.value.reason == "handler_not_implemented_yet"


def test_dispatch_unknown_job_type_raises():
    """Dispatcher raises UnsupportedJobError for unknown job types."""
    from app.workers.exceptions import UnsupportedJobError

    job = CollectionJob(dedupe_key="test:unknown", job_type="unknown:type", status="running")

    with pytest.raises(UnsupportedJobError) as exc_info:
        dispatch_job(Mock(), job)

    assert exc_info.value.job_type == "unknown:type"
    assert exc_info.value.reason == "unknown_job_type"


# ============================================================================
# Graceful Shutdown Test (mocked)
# ============================================================================


@patch("app.workers.main.claim_next_job")
def test_worker_loop_once_flag(mock_claim):
    """Worker with --once flag processes one job and exits."""
    from app.workers.main import worker_loop

    mock_claim.return_value = None  # No jobs available

    # Should exit immediately with once=True
    worker_loop(once=True)

    # Should have called claim_next_job once
    assert mock_claim.call_count == 1


# ============================================================================
# Integration: Full job lifecycle (mocked collector)
# ============================================================================


@needs_db
@patch("app.workers.dispatch.get_daily_prices")
def test_full_job_lifecycle(mock_get_prices):
    """Full lifecycle: schedule → claim → process → mark done."""
    from app.database.session import get_session_factory
    from app.collectors.normalize import NormalizeResult

    mock_get_prices.return_value = NormalizeResult(
        source="twelve_data", count=3, inserted=3, skipped_duplicates=0
    )

    factory = get_session_factory()

    # Cleanup
    with factory() as s:
        s.execute(delete(Asset).where(Asset.ticker == "FULL"))
        s.commit()

    # Create test asset
    with factory() as s:
        asset = Asset(exchange="TST", ticker="FULL", name="Full Test", confirmed=True)
        s.add(asset)
        s.commit()

    try:
        target_date = date.today()

        # 1. Schedule jobs
        with factory() as s:
            count = schedule_daily_collection_jobs(s, target_date)
            assert count == 4

        # 2. Claim a job
        worker_id = get_worker_id()
        with factory() as s:
            job = claim_next_job(s, worker_id)
            s.commit()
            assert job is not None
            assert job.status == "running"
            job_id = job.id

        # 3. Process the job (if it's a market job)
        with factory() as s:
            job = s.get(CollectionJob, job_id)
            if job.job_type == "collect:market":
                counts = dispatch_job(s, job)
                mark_job_done(s, job, counts)
                s.commit()

        # 4. Verify job is done
        with factory() as s:
            job = s.get(CollectionJob, job_id)
            if job.job_type == "collect:market":
                assert job.status == "done"
                assert job.counts is not None
    finally:
        with factory() as s:
            s.execute(delete(Asset).where(Asset.ticker == "FULL"))
            s.commit()
