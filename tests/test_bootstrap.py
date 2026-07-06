"""Application composition root: adapter selection is configuration-only."""

from __future__ import annotations

import json

from bootstrap import build_application
from code_intelligence.infrastructure.fallback_searcher import FallbackCodeSearcher
from code_intelligence.infrastructure.filesystem_searcher import (
    FilesystemCodeSearcher,
)
from code_intelligence.infrastructure.tree_sitter_searcher import (
    TreeSitterCodeSearcher,
)
from shared_kernel.config.settings import Settings

from tests.support.fakes import FakeProvider


def _settings(monkeypatch, **env) -> Settings:
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    return Settings()


def test_default_wiring_uses_tree_sitter_and_no_github(monkeypatch):
    settings = _settings(
        monkeypatch, CODE_SEARCHER=None, GITHUB_TOKEN=None, GITHUB_REPO=None
    )
    app = build_application(settings=settings, provider=FakeProvider())

    # Default searcher: tree-sitter primary with filesystem fallback (R-09).
    assert isinstance(app.code_searcher, FallbackCodeSearcher)
    assert isinstance(app.code_searcher._primary, TreeSitterCodeSearcher)
    assert isinstance(app.code_searcher._fallback, FilesystemCodeSearcher)
    assert app.issue_reader is None
    assert app.create_pull_request is None
    assert app.generate_fix is not None


def test_filesystem_searcher_selected_by_env(monkeypatch):
    settings = _settings(monkeypatch, CODE_SEARCHER="filesystem")
    app = build_application(settings=settings, provider=FakeProvider())
    assert isinstance(app.code_searcher, FilesystemCodeSearcher)


def test_github_adapters_enabled_when_configured(monkeypatch):
    settings = _settings(
        monkeypatch, GITHUB_TOKEN="ghp_test", GITHUB_REPO="user/project"
    )
    app = build_application(settings=settings, provider=FakeProvider())
    assert app.issue_reader is not None
    assert app.create_pull_request is not None


def test_wired_workflow_runs_end_to_end_with_draft_fix_tool(
    monkeypatch, sample_issue, tmp_path
):
    """The composed app exposes draft_fix and completes a workflow with it."""
    (tmp_path / "login.py").write_text("def login(e):\n    return e\n", encoding="utf-8")
    settings = _settings(
        monkeypatch, CODE_SEARCHER=None, GITHUB_TOKEN=None, GITHUB_REPO=None
    )
    provider = FakeProvider(
        responses=[
            json.dumps(
                {
                    "issue_type": "bug",
                    "affected_area": "auth",
                    "symptoms": "login fails",
                    "severity": "high",
                    "reasoning": "repro present",
                }
            ),
            json.dumps(
                {
                    "action": "draft_fix",
                    "args": {
                        "path": "login.py",
                        "original": "def login(e):\n    return e\n",
                    },
                    "reasoning": "draft the fix",
                }
            ),
            json.dumps(
                {
                    "updated_content": "def login(e):\n    return sanitize(e)\n",
                    "explanation": "sanitize input",
                }
            ),
            json.dumps({"action": "finish", "args": {}, "reasoning": "done"}),
        ]
    )
    app = build_application(settings=settings, provider=provider)

    final = app.run_workflow.execute("wf-42", sample_issue, workspace=str(tmp_path))

    assert final["status"] == "done"
    draft_result = final["tool_results"][0]
    assert draft_result["tool"] == "draft_fix"
    assert draft_result["ok"] is True
    assert "+    return sanitize(e)" in draft_result["result"]["diff"]
    assert draft_result["result"]["applied"] is False
