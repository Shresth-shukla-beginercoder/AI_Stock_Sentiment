---
name: phase-7-correction-plan
description: Implementation plan for Phase 7 correction (handle 'train' job type).
metadata:
  type: project
---

# Phase 7 Correction Plan: Handle Unsupported 'train' Job Type

## Objective
Update the worker dispatcher to recognize the `train` job type without crashing, handle it as a permanent failure (`handler_not_implemented_yet`), and ensure the worker continues processing other jobs.

## Tasks
1.  **Modify `app/workers/dispatch.py`**:
    - Update `dispatch_job` to catch the case for `job_type == 'train'`.
    - Define a specific handler or a mechanism to mark the job as a permanent failure without attempting training logic.
    - Alternatively, modify the dispatch logic to handle unknown types gracefully by raising a specific "PermanentFailure" exception that the main loop can catch.
2.  **Update `app/workers/main.py` (Worker Loop)**:
    - Ensure the exception handling in `worker_loop` distinguishes between `TransientError` (retriable) and `PermanentError` (not retriable).
    - If a permanent failure occurs, update the job status to `failed` and stop retrying.
3.  **Update Tests (`backend/tests/test_phase7_workers.py`)**:
    - Add test cases to verify `train` jobs are marked as permanent failures.
    - Verify unknown types do not crash the worker.
    - Verify processing continues for subsequent jobs.

## Implementation Steps
1.  Define `PermanentFailure` exception in `app/collectors/exceptions.py`.
2.  Modify `dispatch_job` in `app/workers/dispatch.py` to raise `PermanentFailure` for `train` and unknown types.
3.  Update `worker_loop` in `app/workers/main.py` to handle `PermanentFailure`.
4.  Update tests.
5.  Rebuild and verify.
