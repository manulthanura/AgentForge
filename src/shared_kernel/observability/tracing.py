"""LangSmith tracing switch.

LangGraph natively traces every node execution through LangSmith once the
LANGCHAIN_* environment is set; this module owns that decision so tracing is
only enabled when a key is actually configured (a half-configured setup
spams auth errors on every run).
"""

from __future__ import annotations

import logging
import os

from ..config.settings import Settings

logger = logging.getLogger(__name__)


def init_tracing(settings: Settings) -> bool:
    """Enable LangSmith tracing when configured; hard-disable otherwise.

    Returns True when tracing is on. Every LangGraph node run is then
    traced (node name, inputs/outputs, latency, token usage) under
    ``settings.langchain_project``.
    """
    if settings.tracing_enabled and settings.langchain_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
        logger.info(
            "LangSmith tracing enabled (project=%s)", settings.langchain_project
        )
        return True
    if settings.tracing_enabled and not settings.langchain_api_key:
        logger.warning(
            "LANGCHAIN_TRACING_V2 is set but LANGCHAIN_API_KEY is missing; "
            "tracing disabled."
        )
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ["LANGSMITH_TRACING"] = "false"
    return False
