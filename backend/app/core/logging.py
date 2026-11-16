"""Logging setup with secret redaction."""

import json
import logging
import re
import sys
from datetime import UTC, datetime

# Redacts credentials embedded in URLs and common key/value secret patterns.
_URL_CRED = re.compile(r"(\w+(?:\+\w+)?://[^:/\s]+:)[^@\s]+(@)")
_KV_SECRET = re.compile(
    r"(?i)((?:api[_-]?key|token|password|secret|authorization)\"?\s*[=:]\s*\"?)[^\s\",;]+"
)


def redact(text: str) -> str:
    text = _URL_CRED.sub(r"\1***\2", text)
    return _KV_SECRET.sub(r"\1***", text)


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


class JsonFormatter(RedactingFormatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return redact(json.dumps(payload))


def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter()
        if json_logs
        else RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
