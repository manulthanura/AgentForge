"""Graceful degradation: primary search failure falls back (R-09)."""

from __future__ import annotations

from pathlib import Path

import pytest

from code_intelligence.application.ports import CodeSearcher
from code_intelligence.domain.models import CodeLocation, CodeSearchResult
from code_intelligence.infrastructure.fallback_searcher import FallbackCodeSearcher
from code_intelligence.infrastructure.filesystem_searcher import (
    FilesystemCodeSearcher,
)


class BrokenSearcher(CodeSearcher):
    def __init__(self, error=RuntimeError("tree-sitter grammar crashed")):
        self.error = error
        self.calls = 0

    def search(self, query, workspace, max_results=20):
        self.calls += 1
        raise self.error


class StubSearcher(CodeSearcher):
    def __init__(self):
        self.calls = 0

    def search(self, query, workspace, max_results=20):
        self.calls += 1
        return CodeSearchResult(
            query=query, matches=(CodeLocation("a.py", 1, "hit"),)
        )


def test_primary_failure_falls_back():
    primary, fallback = BrokenSearcher(), StubSearcher()
    searcher = FallbackCodeSearcher(primary, fallback)

    result = searcher.search("query", ".")

    assert result.found
    assert primary.calls == 1 and fallback.calls == 1
    assert searcher.fallback_count == 1


def test_healthy_primary_never_touches_fallback():
    primary, fallback = StubSearcher(), StubSearcher()
    searcher = FallbackCodeSearcher(primary, fallback)
    searcher.search("query", ".")
    assert primary.calls == 1 and fallback.calls == 0
    assert searcher.fallback_count == 0


def test_both_failing_propagates_for_the_compound_guard():
    searcher = FallbackCodeSearcher(
        BrokenSearcher(), BrokenSearcher(RuntimeError("disk on fire"))
    )
    with pytest.raises(RuntimeError, match="disk on fire"):
        searcher.search("query", ".")


def test_fallback_to_real_filesystem_searcher(tmp_path: Path):
    (tmp_path / "login.py").write_text("email = raw\n", encoding="utf-8")
    searcher = FallbackCodeSearcher(BrokenSearcher(), FilesystemCodeSearcher())
    result = searcher.search("email", tmp_path)
    assert result.found
    assert result.matches[0].file == "login.py"
