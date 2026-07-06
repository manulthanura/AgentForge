"""Ports (interfaces) the code intelligence use cases depend on."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..domain.models import CodeSearchResult


class CodeSearcher(ABC):
    @abstractmethod
    def search(
        self, query: str, workspace: str | Path, max_results: int = 20
    ) -> CodeSearchResult:
        """Find code locations matching the query inside the workspace."""
