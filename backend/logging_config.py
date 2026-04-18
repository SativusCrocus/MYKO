"""Structured JSON audit logging.

Audit entries are written to ``~/MYKO/logs/audit.jsonl`` (rotated at 10 MB,
5 backups) and also mirrored to ``stderr`` so the MCP server can keep stdout
reserved exclusively for JSON-RPC traffic.

Never log raw plaintext, keys, passphrases, macaroons, or Lightning preimages.
Inputs and outputs are represented as SHA-256 hashes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

AUDIT_FIELDS = ("action", "tool", "input_hash", "output_hash", "ok", "error")


class AuditJSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for attr in AUDIT_FIELDS:
            if hasattr(record, attr):
                payload[attr] = getattr(record, attr)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def sha256_hex(data: Any) -> str:
    """Hash arbitrary data (bytes / str / JSON-serializable) with SHA-256."""
    if isinstance(data, (bytes, bytearray)):
        buf = bytes(data)
    elif isinstance(data, str):
        buf = data.encode("utf-8")
    else:
        buf = json.dumps(data, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(buf).hexdigest()


def configure_logging(home: Path, level: str = "INFO") -> logging.Logger:
    """Configure the root ``myko`` logger with an audit file + stderr handler."""
    logs_dir = Path(home).expanduser() / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    audit_path = logs_dir / "audit.jsonl"

    logger = logging.getLogger("myko")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.handlers.clear()
    logger.propagate = False

    file_handler = RotatingFileHandler(
        audit_path,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(AuditJSONFormatter())
    logger.addHandler(file_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(stderr_handler)

    return logger
