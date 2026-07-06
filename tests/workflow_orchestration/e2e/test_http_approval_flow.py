"""Full HTTP approval flow against the docker-compose stack.

Exercises features/approval.feature end-to-end: a signed GitHub webhook
starts a workflow that pauses at the approval gate (checkpointed in the
compose Postgres); a signed Slack interaction approves or rejects it; the
workflow resumes from its checkpoint with full state (F-07). Forged
signatures are rejected (S-06).

Skipped automatically when the compose Postgres is unreachable.
"""

from __future__ import annotations

import json
import os
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from approval.domain.models import ApprovalStatus
from approval.infrastructure.postgres_approval_repo import PostgresApprovalRepository
from bootstrap import build_application
from interfaces.http.app import create_app
from shared_kernel.config.settings import Settings
from shared_kernel.persistence.migrate import run_migrations

from tests.support.fakes import FakeProvider
from tests.support.signing import (
    github_headers,
    github_issue_event,
    slack_interaction,
)

DEFAULT_URL = "postgresql://user:pass@localhost:5432/agentforge"
PG_URL = os.environ.get("DATABASE_URL", DEFAULT_URL)
GH_SECRET = "gh-e2e-secret"
SLACK_SECRET = "slack-e2e-secret"


def _postgres_available() -> bool:
    try:
        psycopg.connect(PG_URL, connect_timeout=2).close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _postgres_available(),
    reason=f"PostgreSQL not reachable at {PG_URL} (docker compose up to enable)",
)


ANALYSIS_BUG = json.dumps(
    {
        "issue_type": "bug",
        "affected_area": "authentication",
        "symptoms": "login failure with special characters",
        "severity": "high",
        "reasoning": "Reproduction steps included.",
    }
)


def _route(action, reasoning="next"):
    return json.dumps({"action": action, "args": {}, "reasoning": reasoning})


@pytest.fixture(scope="module", autouse=True)
def migrated_db():
    run_migrations(PG_URL)


@pytest.fixture
def client(monkeypatch):
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg import Connection
    from psycopg.rows import dict_row

    monkeypatch.setenv("REQUIRE_APPROVAL", "true")
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", GH_SECRET)
    monkeypatch.setenv("SLACK_SIGNING_SECRET", SLACK_SECRET)
    monkeypatch.setenv("DATABASE_URL", PG_URL)
    settings = Settings()

    conn = Connection.connect(PG_URL, autocommit=True, row_factory=dict_row)
    checkpointer = PostgresSaver(conn)
    provider = FakeProvider(
        responses=[ANALYSIS_BUG, _route("finish"), _route("finish")]
    )
    application = build_application(
        settings=settings,
        provider=provider,
        checkpointer=checkpointer,
        approval_repository=PostgresApprovalRepository(PG_URL),
    )
    app = create_app(application=application, settings=settings)
    with TestClient(app) as test_client:
        yield test_client
    conn.close()


def _open_issue(client, number: int) -> dict:
    body = github_issue_event(
        number,
        "Login fails when email contains '+' character",
        "Steps to reproduce: register with alice+test@example.com",
        ["bug"],
    )
    response = client.post(
        "/webhooks/github", content=body, headers=github_headers(GH_SECRET, body)
    )
    assert response.status_code == 200
    return response.json()


def test_full_pause_approve_flow(client):
    number = int(uuid.uuid4().int % 1_000_000) + 1000
    workflow_id = f"issue-{number}"

    # 1. Signed webhook starts the workflow; it pauses at the approval gate.
    started = _open_issue(client, number)
    assert started == {
        "workflow_id": workflow_id,
        "status": "awaiting_approval",
        "classification": "bug",
        "awaiting_approval": True,
    }

    # 2. The approval request is persisted in the compose Postgres.
    repo = PostgresApprovalRepository(PG_URL)
    assert repo.get(workflow_id).status is ApprovalStatus.PENDING

    # 3. A forged Slack approval is rejected (S-06) and nothing resumes.
    body, headers = slack_interaction("wrong-secret", "approve", workflow_id)
    assert (
        client.post(
            "/webhooks/slack/interactions", content=body, headers=headers
        ).status_code
        == 401
    )
    assert client.get(f"/workflows/{workflow_id}").json()["status"] == (
        "awaiting_approval"
    )

    # 4. The genuine approval resumes from the checkpoint and completes.
    body, headers = slack_interaction(SLACK_SECRET, "approve", workflow_id)
    response = client.post(
        "/webhooks/slack/interactions", content=body, headers=headers
    )
    assert response.status_code == 200
    assert response.json()["status"] == "done"

    # 5. Full state survived the pause (F-07): analysis + decision trail.
    status = client.get(f"/workflows/{workflow_id}").json()
    assert status["status"] == "done"
    nodes = [d["node"] for d in status["decisions"]]
    assert "notify_approval" in nodes and "await_approval" in nodes
    assert repo.get(workflow_id).status is ApprovalStatus.APPROVED


def test_rejection_with_feedback_pauses_again(client):
    number = int(uuid.uuid4().int % 1_000_000) + 2_000_000
    workflow_id = f"issue-{number}"
    _open_issue(client, number)

    body, headers = slack_interaction(
        SLACK_SECRET, "reject", workflow_id, feedback="Try a different approach"
    )
    response = client.post(
        "/webhooks/slack/interactions", content=body, headers=headers
    )
    assert response.status_code == 200
    # Router re-ran with the feedback, chose finish again -> paused again.
    assert response.json()["status"] == "awaiting_approval"

    status = client.get(f"/workflows/{workflow_id}").json()
    rejected = [d for d in status["decisions"] if d["action"] == "rejected"]
    assert rejected and "Try a different approach" in rejected[0]["reasoning"]
