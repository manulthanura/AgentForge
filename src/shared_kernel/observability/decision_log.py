"""Structured decision logging: why did the agent choose this action?

Each decision is emitted as one JSON line on the ``agentforge.decisions``
logger, so any log pipeline (or plain grep) can reconstruct the agent's
reasoning chain independently of LangSmith.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Mapping


class DecisionLogger:
    def __init__(self, logger: logging.Logger | None = None):
        self._logger = logger or logging.getLogger("agentforge.decisions")

    def log(self, workflow_id: str, decision: Mapping[str, Any]) -> None:
        self._logger.info(
            json.dumps(
                {"workflow_id": workflow_id, **decision}, default=str
            )
        )
