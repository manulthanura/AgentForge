"""Use case: find code relevant to an issue."""

from __future__ import annotations

from pathlib import Path

from ..domain.models import CodeSearchResult
from .ports import CodeSearcher


class SearchRelevantCodeUseCase:
    def __init__(self, searcher: CodeSearcher):
        self._searcher = searcher

    def execute(
        self, query: str, workspace: str | Path, max_results: int = 20
    ) -> CodeSearchResult:
        return self._searcher.search(query, workspace, max_results=max_results)
