"""Structured logging.

JSON-formatted lines so logs stay machine-parseable and grep-able.
Redaction scrub *values* of secrets out of messages while preserving credential
names (e.g. ``missing_credentials=API_ADMIN_KEY`` must stay readable — it logs
names only, never values).
"""

import json
import logging
import re
import sys
from datetime import datetime, timezone

# Redact the VALUE that follows a key-name =/quotes, but keep the name.
# Also redact well-known provider token shapes directly.
_PATTERNS = [
    # name=value where name looks like a credential -> keep name, drop value
    (
        re.compile(
            r"((?:api_?key|admin_?key|access_?key|token|secret|password)"
            r"[^,\s]*)[=:]\s*[\"']?[A-Za-z0-9_\-./+]{6,}[\"']?",
            re.IGNORECASE,
        ),
        r"\1=[REDACTED]",
    ),
    # Apify tokens
    (re.compile(r"apify_api_[A-Za-z0-9]{6,}"), "[REDACTED]"),
    # Tavily tokens
    (re.compile(r"tvly-[a-z]+-[A-Za-z0-9=]{6,}"), "[REDACTED]"),
    # 40-hex API keys
    (re.compile(r"\b[0-9a-f]{40}\b", re.IGNORECASE), "[REDACTED]"),
    # Generic UUID-shaped secrets
    (
        re.compile(
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
        ),
        "[REDACTED]",
    ),
]


def redact(message: str) -> str:
    out = message
    for rx, repl in _PATTERNS:
        out = rx.sub(repl, out)
    return out


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact(record.msg)
        elif record.args:
            record.msg = redact(record.getMessage())
            record.args = None
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return redact(json.dumps(payload, ensure_ascii=False))


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Keep third-party loggers at WARNING to avoid noise
    for noisy in ("uvicorn.access", "uvicorn.error", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
