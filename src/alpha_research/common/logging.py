from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path


class JsonLogFormatter(logging.Formatter):
    """Minimal structured JSON formatter."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def configure_logging(log_dir: Path, run_id: str, level: int = logging.INFO) -> logging.Logger:
    """Configure console and file JSON logging for the current run."""

    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("alpha_research")
    logger.setLevel(level)
    logger.handlers.clear()
    logger.propagate = False

    formatter = JsonLogFormatter()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = logging.FileHandler(log_dir / f"{run_id}.jsonl", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
