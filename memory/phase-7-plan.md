---
name: phase-7-plan
description: Implementation plan for Phase 7: Workers and Scheduling.
metadata:
  type: project
---

# Phase 7 Plan: Workers and Scheduling

## Objective
Implement background job processing for data collection and sentiment analysis using PostgreSQL-based queueing.

## Files to be created/modified
- `backend/app/workers/main.py`: Main worker loop, `--once` support, signal handling (SIGTERM).
- `backend/app/workers/claim.py`: Job claiming logic using `FOR UPDATE SKIP LOCKED`.
- `backend/app/workers/scheduler.py`: Job scheduling with advisory locks (`pg_try_advisory_lock`).
- `backend/app/workers/reaper.py`: Cleanup for stuck running jobs.
- `backend/app/workers/dispatch.py`: Handler routing.
- `docker-compose.yml`: Add `worker` service.
- `backend/tests/test_phase7_workers.py`: Comprehensive test suite.

## Risks & Mitigation
- **Race conditions**: Mitigated by `FOR UPDATE SKIP LOCKED` and advisory locks.
- **Graceful shutdown**: Handled via custom signal handlers to complete/abort current job.
- **Stuck jobs**: Mitigated by a reaper that detects jobs running longer than a timeout.

## Implementation Steps
1. Define job states in `models.py` (if not already sufficient).
2. Implement `claim.py` and `reaper.py`.
3. Implement `scheduler.py` for periodic tasks.
4. Implement `dispatch.py` for handling specific job types.
5. Implement `main.py` entry point.
6. Update `docker-compose.yml`.
7. Write and run tests.
8. Verify and update documentation.
