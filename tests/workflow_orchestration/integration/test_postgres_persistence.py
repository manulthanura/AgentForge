"""PostgreSQL integration: migrations, workflow repo, checkpoint round-trip.

These tests run against the docker-compose Postgres (or any DATABASE_URL).
They are skipped automatically when no database is reachable, so the suite
still passes in environments without Docker.
"""

from __future__ import annotations

import json
import os
import uuid

import psycopg
import pytest

from shared_kernel.persistence.migrate import run_migrations
from workflow_orchestration.domain.models import AgentWorkflow, WorkflowStatus
from workflow_orchestration.infrastructure.postgres_workflow_repo import (
    PostgresWorkflowRepository,
)

from tests.support.fakes import FakeProvider

DEFAULT_URL = "postgresql://user:pass@localhost:5432/agentforge"
PG_URL = os.environ.get("DATABASE_URL", DEFAULT_URL)


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


@pytest.fixture(scope="module", autouse=True)
def migrated_db():
    run_migrations(PG_URL)


def test_migrations_are_idempotent():
    # First run happened in the fixture; a second run applies nothing new.
    assert run_migrations(PG_URL) == []
    with psycopg.connect(PG_URL) as conn:
        versions = [
            r[0] for r in conn.execute("SELECT version FROM schema_migrations")
        ]
    assert "0001_workflows.sql" in versions


def test_workflow_repository_roundtrip(sample_issue):
    repo = PostgresWorkflowRepository(PG_URL)
    workflow_id = f"test-{uuid.uuid4().hex[:8]}"

    repo.upsert(AgentWorkflow(workflow_id=workflow_id, issue=sample_issue))
    row = repo.get(workflow_id)
    assert row.status is WorkflowStatus.ANALYZING
    assert row.issue["number"] == 42

    repo.upsert(
        AgentWorkflow(
            workflow_id=workflow_id,
            issue=sample_issue,
            status=WorkflowStatus.DONE,
            classification="bug",
        )
    )
    row = repo.get(workflow_id)
    assert row.status is WorkflowStatus.DONE
    assert row.classification == "bug"

    assert any(
        w.workflow_id == workflow_id for w in repo.list(status="done")
    )


def test_langgraph_checkpoint_roundtrip_in_postgres(sample_issue):
    from langgraph.checkpoint.postgres import PostgresSaver

    from workflow_orchestration.bootstrap import build_agent_graph

    analysis = json.dumps(
        {
            "issue_type": "bug",
            "affected_area": "auth",
            "symptoms": "login fails",
            "severity": "high",
            "reasoning": "repro steps present",
        }
    )
    finish = json.dumps({"action": "finish", "args": {}, "reasoning": "done"})

    thread_id = f"pg-test-{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}
    initial = {
        "workflow_id": thread_id,
        "issue": sample_issue,
        "status": "analyzing",
        "step_count": 0,
    }

    with PostgresSaver.from_conn_string(PG_URL) as checkpointer:
        graph = build_agent_graph(
            FakeProvider(responses=[analysis, finish]), checkpointer=checkpointer
        )
        final = graph.invoke(initial, config)
        assert final["status"] == "done"

    # Re-open a fresh connection: the checkpoint survives process boundaries.
    with PostgresSaver.from_conn_string(PG_URL) as checkpointer:
        graph = build_agent_graph(FakeProvider(), checkpointer=checkpointer)
        snapshot = graph.get_state(config)
        assert snapshot.values["status"] == "done"
        assert snapshot.values["workflow_id"] == thread_id
