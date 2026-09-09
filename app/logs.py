"""File logging into the data directory.

Writes `<data>/lettermatch.log` (rotated). The access log keeps real page hits
(`/`, `/compare`) and drops the noise: health checks, poster proxy, static files.
The `lettermatch` logger adds one line per comparison saying, per user, whether
the film list came from the cache or was freshly scraped.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from .config import LOG_LEVEL, LOG_PATH

_NOISE = ("/healthz", "/poster/", "/static/", "/favicon")


class _DropNoise(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(p in msg for p in _NOISE)


def setup_logging() -> logging.Logger:
    os.makedirs(os.path.dirname(LOG_PATH) or ".", exist_ok=True)

    handler = RotatingFileHandler(
        LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s | %(message)s", "%Y-%m-%d %H:%M:%S"
    ))
    handler.addFilter(_DropNoise())
    handler.setLevel(LOG_LEVEL)

    for name in ("lettermatch", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        if not any(isinstance(h, RotatingFileHandler) for h in lg.handlers):
            lg.addHandler(handler)
        if lg.level == logging.NOTSET or lg.level > logging.INFO:
            lg.setLevel("INFO")

    logger = logging.getLogger("lettermatch")
    logger.info("logging to %s (level %s)", LOG_PATH, LOG_LEVEL)
    return logger
