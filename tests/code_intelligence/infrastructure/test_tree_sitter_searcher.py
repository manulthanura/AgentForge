"""TreeSitterCodeSearcher: AST-aware matching and relevance ranking (F-02)."""

from __future__ import annotations

import pytest

from code_intelligence.application.ports import CodeSearcher
from code_intelligence.infrastructure.tree_sitter_searcher import (
    TreeSitterCodeSearcher,
)


@pytest.fixture
def searcher():
    return TreeSitterCodeSearcher()


@pytest.fixture
def workspace(tmp_path):
    """A miniature repo mirroring the F-02 scenario."""
    (tmp_path / "src" / "auth").mkdir(parents=True)
    (tmp_path / "src" / "utils").mkdir(parents=True)
    (tmp_path / "tests").mkdir()
    # Primary: defines the matching function.
    (tmp_path / "src" / "auth" / "login.py").write_text(
        "def validate_email(email):\n"
        "    # email validation entry point\n"
        "    return '@' in email\n",
        encoding="utf-8",
    )
    # Secondary: references it once.
    (tmp_path / "src" / "utils" / "validators.py").write_text(
        "from src.auth.login import validate_email\n",
        encoding="utf-8",
    )
    # Reference: mentions it in a test.
    (tmp_path / "tests" / "test_auth.py").write_text(
        "def test_login():\n    assert validate_email('a@b.c')\n",
        encoding="utf-8",
    )
    # Noise: unrelated file that must not appear.
    (tmp_path / "README.md").write_text("project readme", encoding="utf-8")
    return tmp_path


def test_implements_the_same_port_as_filesystem_searcher(searcher):
    assert isinstance(searcher, CodeSearcher)


def test_ranks_defining_file_first(searcher, workspace):
    result = searcher.search("validate_email", workspace)

    ranked = [f.file for f in result.ranked_files]
    # The file defining validate_email() outranks files merely referencing it.
    assert ranked[0].endswith("login.py")
    assert len(ranked) == 3  # noise file excluded
    scores = [f.score for f in result.ranked_files]
    assert scores == sorted(scores, reverse=True)
    # Matches are ordered by file rank, definition line first.
    assert result.matches[0].file.endswith("login.py")
    assert result.matches[0].line == 1


def test_multi_term_query_matches_path_and_content(searcher, workspace):
    result = searcher.search("authentication email validation", workspace)
    ranked = [f.file for f in result.ranked_files]
    # "validation"/"email" hit login.py and validators.py content + paths.
    assert any(f.endswith("login.py") for f in ranked)
    assert any(f.endswith("validators.py") for f in ranked)


def test_missing_workspace_reports_error(searcher):
    result = searcher.search("anything", "Z:/definitely/not/a/dir")
    assert not result.found
    assert result.error is not None


def test_no_matches_returns_empty_ranking(searcher, workspace):
    result = searcher.search("nonexistent_module_xyz", workspace)
    assert result.matches == ()
    assert result.ranked_files == ()


def test_truncation_respects_max_results(searcher, tmp_path):
    (tmp_path / "big.py").write_text(
        "def target():\n" + "target = 1\n" * 30, encoding="utf-8"
    )
    (tmp_path / "other.py").write_text("target = 2\n" * 30, encoding="utf-8")
    result = searcher.search("target", tmp_path, max_results=3)
    assert len(result.matches) == 3
    assert result.truncated is True
    # Ranking still covers every relevant file even when matches truncate.
    assert len(result.ranked_files) == 2


def test_non_python_files_fall_back_to_line_scan(searcher, tmp_path):
    (tmp_path / "config.yaml").write_text("email_validation: on\n", encoding="utf-8")
    result = searcher.search("email_validation", tmp_path)
    assert result.found
    assert result.matches[0].file == "config.yaml"


def test_search_result_dict_includes_ranking(searcher, workspace):
    payload = searcher.search("validate_email", workspace).to_dict()
    assert payload["ranked_files"][0]["file"].endswith("login.py")
    assert payload["ranked_files"][0]["score"] > 0
