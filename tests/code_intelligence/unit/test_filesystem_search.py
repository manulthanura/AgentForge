"""Filesystem code searcher and search use case."""

from __future__ import annotations

from code_intelligence.application.search_relevant_code import (
    SearchRelevantCodeUseCase,
)
from code_intelligence.infrastructure.filesystem_searcher import (
    FilesystemCodeSearcher,
)


def _use_case() -> SearchRelevantCodeUseCase:
    return SearchRelevantCodeUseCase(FilesystemCodeSearcher())


def test_search_finds_matches(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "login.py").write_text(
        "def validate_email(email):\n    return '@' in email\n", encoding="utf-8"
    )
    (tmp_path / "README.md").write_text("nothing here", encoding="utf-8")

    result = _use_case().execute("validate_email", tmp_path)

    assert result.found
    assert len(result.matches) == 1
    assert result.matches[0].file.endswith("login.py")
    assert result.matches[0].line == 1
    assert result.truncated is False
    assert result.to_dict()["matches"][0]["line"] == 1


def test_search_missing_workspace():
    result = _use_case().execute("anything", "Z:/definitely/not/a/dir")
    assert not result.found
    assert result.error is not None
    assert "error" in result.to_dict()


def test_search_invalid_regex_falls_back_to_literal(tmp_path):
    (tmp_path / "a.txt").write_text("weird [pattern here", encoding="utf-8")
    result = _use_case().execute("[pattern", tmp_path)
    assert len(result.matches) == 1


def test_search_truncates_at_max_results(tmp_path):
    (tmp_path / "big.txt").write_text("match\n" * 50, encoding="utf-8")
    result = _use_case().execute("match", tmp_path, max_results=5)
    assert len(result.matches) == 5
    assert result.truncated is True
