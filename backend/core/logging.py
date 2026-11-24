"""Structured JSON logging with request correlation and credential redaction."""

import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

SENSITIVE_KEYS = re.compile(
    r"(password|secret|token|authorization|api[_-]?key|private[_-]?key)", re.IGNORECASE
)
BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
JWT_LIKE = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


def redact(value: Any) -> Any:
    """Return a copy with credential-like keys and token-like strings masked."""
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if SENSITIVE_KEYS.search(str(k)) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return JWT_LIKE.sub("[REDACTED]", BEARER.sub(r"\1[REDACTED]", value))
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_var.get(),
            "message": redact(record.getMessage()),
        }
        extra = getattr(record, "data", None)
        if isinstance(extra, dict):
            entry["data"] = redact(extra)
        if record.exc_info and record.exc_info[0] is not None:
            entry["exception"] = record.exc_info[0].__name__
        return json.dumps(entry, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger("backend")
    root.handlers[:] = [handler]
    root.setLevel(level)
    root.propagate = False
