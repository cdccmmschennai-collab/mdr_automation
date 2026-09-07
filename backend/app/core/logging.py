"""Logging setup.

One function, called once at process start (CLI or API). The engine itself
does not log: every Phase 1 decision is carried on the record as a `reason`,
which is auditable in a way that a log line is not.
"""

from __future__ import annotations

import logging

from .config import settings

_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"


def configure_logging(level: str | None = None) -> None:
    """Configure root logging. Idempotent - safe to call more than once."""
    logging.basicConfig(
        level=getattr(logging, (level or settings.log_level), logging.INFO),
        format=_FORMAT,
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
