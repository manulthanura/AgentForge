"""FastAPI assembly: routers, signature enforcement, and the admin API."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from bootstrap import build_application
from interfaces.http.app import create_app
from shared_kernel.config.model_config import ModelConfigStore
from shared_kernel.config.settings import Settings

from tests.support.fakes import FakeProvider
from tests.support.signing import github_headers, github_issue_event

GH_SECRET = "gh-secret"
ADMIN_KEY = "admin-key"

ANALYSIS_VAGUE = json.dumps(
    {
        "issue_type": "insufficient_information",
        "affected_area": "unknown",
        "symptoms": "unspecified",
        "severity": "low",
        "reasoning": "No details.",
    }
)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", GH_SECRET)
    monkeypatch.setenv("SECRET_KEY", ADMIN_KEY)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings()
    application = build_application(
        settings=settings,
        provider=FakeProvider(responses=[ANALYSIS_VAGUE]),
        checkpointer=InMemorySaver(),
    )
    config_path = tmp_path / "model_config.json"
    config_path.write_text('{"anthropic": "claude-opus-4-8"}', encoding="utf-8")
    app = create_app(
        application=application,
        settings=settings,
        model_config_store=ModelConfigStore(config_path),
    )
    return TestClient(app)


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["provider"] == "fake"


def test_forged_github_webhook_rejected(client):
    body = github_issue_event(43, "It doesn't work", "please fix", [])
    headers = github_headers("wrong-secret", body)
    assert client.post("/webhooks/github", content=body, headers=headers).status_code == 401


def test_signed_github_webhook_starts_workflow(client):
    body = github_issue_event(43, "It doesn't work", "please fix", [])
    response = client.post(
        "/webhooks/github", content=body, headers=github_headers(GH_SECRET, body)
    )
    assert response.status_code == 200
    data = response.json()
    assert data["workflow_id"] == "issue-43"
    assert data["status"] == "awaiting_clarification"

    status = client.get("/workflows/issue-43").json()
    assert status["status"] == "awaiting_clarification"
    assert status["decisions"]


def test_non_issue_events_ignored(client):
    body = b'{"action": "opened"}'
    headers = github_headers(GH_SECRET, body) | {"X-GitHub-Event": "push"}
    response = client.post("/webhooks/github", content=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["ignored"] is True


def test_unknown_workflow_status_404(client):
    assert client.get("/workflows/ghost").status_code == 404


# --- Admin model-config ------------------------------------------------------


def test_admin_requires_token(client):
    response = client.patch(
        "/admin/model-config",
        json={"provider": "anthropic", "model": "claude-x"},
    )
    assert response.status_code == 401


def test_admin_patch_updates_store(client):
    headers = {"X-Admin-Token": ADMIN_KEY}
    response = client.patch(
        "/admin/model-config",
        json={"provider": "anthropic", "model": "claude-tuned"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["anthropic"] == "claude-tuned"
    assert client.get("/admin/model-config", headers=headers).json()[
        "anthropic"
    ] == "claude-tuned"


def test_admin_rejects_unknown_provider(client):
    response = client.patch(
        "/admin/model-config",
        json={"provider": "grok", "model": "x"},
        headers={"X-Admin-Token": ADMIN_KEY},
    )
    assert response.status_code == 422
