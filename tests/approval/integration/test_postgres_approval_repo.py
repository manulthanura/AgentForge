"""PostgresApprovalRepository round-trip against the compose database."""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from approval.domain.models import ApprovalRequest, ApprovalStatus
from approval.infrastructure.postgres_approval_repo import PostgresApprovalRepository
from shared_kernel.persistence.migrate import run_migrations

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


def test_approval_request_roundtrip():
    repo = PostgresApprovalRepository(PG_URL)
    workflow_id = f"apr-{uuid.uuid4().hex[:8]}"

    repo.save(ApprovalRequest(workflow_id=workflow_id, action="finalize_workflow"))
    stored = repo.get(workflow_id)
    assert stored.status is ApprovalStatus.PENDING
    assert any(r.workflow_id == workflow_id for r in repo.list_pending())

    repo.save(stored.decide(approved=False, feedback="try again"))
    decided = repo.get(workflow_id)
    assert decided.status is ApprovalStatus.REJECTED
    assert decided.feedback == "try again"
    assert decided.decided_at is not None
    assert all(r.workflow_id != workflow_id for r in repo.list_pending())
