"""Custom exceptions for the worker system."""

class WorkerError(Exception):
    """Base class for worker-related errors."""
    pass

class UnsupportedJobError(WorkerError):
    """Raised when a job type is not supported.

    Terminal, machine-readable failure: the worker marks the job as
    permanently failed (no retry) and continues with other jobs.

    ``reason`` values:
    - ``handler_not_implemented_yet``: job type is known but its handler
      belongs to a later phase (e.g. ``train`` is Phase 8).
    - ``unknown_job_type``: no handler is registered for the type.
    """

    def __init__(self, job_type: str, reason: str = "handler_not_implemented_yet",
                 detail: str = "") -> None:
        self.job_type = job_type
        self.reason = reason
        self.detail = detail
        msg = f"Unsupported job type: {job_type} ({reason})"
        if detail:
            msg += f" — {detail}"
        super().__init__(msg)
