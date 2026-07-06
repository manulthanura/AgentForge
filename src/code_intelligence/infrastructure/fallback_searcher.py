"""Graceful degradation for code search (R-09).

Tries the primary searcher (tree-sitter); if it raises, logs and falls back
to the secondary (filesystem scan). Only when both fail does the error
propagate — the workflow's compound-failure guard then decides whether to
escalate.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..application.ports import CodeSearcher
from ..domain.models import CodeSearchResult

logger = logging.getLogger(__name__)


class FallbackCodeSearcher(CodeSearcher):
    def __init__(self, primary: CodeSearcher, fallback: CodeSearcher):
        self._primary = primary
        self._fallback = fallback
        # Exposed for tests/observability: how often the fallback engaged.
        self.fallback_count = 0

    def search(
        self, query: str, workspace: str | Path, max_results: int = 20
    ) -> CodeSearchResult:
        try:
            return self._primary.search(query, workspace, max_results=max_results)
        except Exception as exc:  # noqa: BLE001 — degrade, don't die
            self.fallback_count += 1
            logger.warning(
                "Primary code search (%s) failed (%s); falling back to %s",
                type(self._primary).__name__,
                exc,
                type(self._fallback).__name__,
            )
            return self._fallback.search(query, workspace, max_results=max_results)
