"""Console logging setup.

Without this, application `logger.info(...)` calls (decision log entries,
comment-hook confirmations, etc.) never reach the console — Python's root
logger defaults to WARNING with no handler, so only uvicorn's own request
lines and warning/error-level messages show up.
"""

from __future__ import annotations

import logging

from ..config.settings import Settings


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
