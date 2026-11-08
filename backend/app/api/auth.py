"""Admin API-key authentication.

- Header: ``X-API-Key`` (CLAUDE.md design constant).
- Checked with ``secrets.compare_digest`` (constant-time; no timing leaks).
- 401 when the key is missing, or when the configured admin key is unset.
- The key value is never logged.
"""

import secrets

from fastapi import Header

from app.core.config import get_settings
from app.schemas.envelope import APIError


def require_admin(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    settings = get_settings()
    expected = settings.api_admin_key
    if expected is None:
        raise APIError(
            401,
            "admin_not_configured",
            "Admin API key is not configured on this backend; protected endpoints are disabled.",
        )
    if not x_api_key or not secrets.compare_digest(expected.get_secret_value(), x_api_key):
        raise APIError(401, "unauthorized", "Invalid or missing admin API key (X-API-Key).")
