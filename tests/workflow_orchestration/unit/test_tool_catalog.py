"""Tool catalog wiring: names, descriptions, and cross-context delegation."""

from __future__ import annotations

import pytest

from code_intelligence.application.search_relevant_code import (
    SearchRelevantCodeUseCase,
)
from code_intelligence.infrastructure.filesystem_searcher import (
    FilesystemCodeSearcher,
)
from fix_generation.application.propose_fix import ProposeFixUseCase
from workflow_orchestration.application.tools import build_default_catalog


@pytest.fixture
def catalog():
    return build_default_catalog(
        search_code=SearchRelevantCodeUseCase(FilesystemCodeSearcher()),
        propose_fix=ProposeFixUseCase(),
    )


def test_catalog_contents(catalog):
    assert set(catalog.names()) == {"read_issue", "search_code", "propose_edit"}
    description = catalog.describe()
    assert "search_code" in description and "query" in description


def test_unknown_tool_raises(catalog):
    with pytest.raises(KeyError, match="no_such_tool"):
        catalog.get("no_such_tool")


def test_read_issue_delegates_to_issue_domain(catalog, sample_issue):
    result = catalog.get("read_issue").handler(issue=sample_issue)
    assert result["number"] == 42
    assert result["labels"] == ["bug"]


def test_search_code_delegates_to_code_intelligence(catalog, tmp_path):
    (tmp_path / "login.py").write_text("email = raw\n", encoding="utf-8")
    result = catalog.get("search_code").handler(
        query="email", workspace=str(tmp_path)
    )
    assert result["matches"] and result["matches"][0]["file"] == "login.py"


def test_propose_edit_delegates_to_fix_generation(catalog):
    result = catalog.get("propose_edit").handler(
        path="a.py", original="x = 1\n", updated="x = 2\n"
    )
    assert result["applied"] is False
    assert "+x = 2" in result["diff"]
