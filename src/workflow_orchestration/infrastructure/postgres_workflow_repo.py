"""PostgreSQL implementation of the WorkflowRepository port."""

from __future__ import annotations

import json
import logging

import psycopg
from psycopg.rows import dict_row

from ..application.ports import WorkflowRepository
from ..domain.models import AgentWorkflow, WorkflowStatus

logger = logging.getLogger(__name__)


class CorruptedWorkflowStateError(RuntimeError):
    """A persisted workflow row failed validation (R-08).

    The durable step-by-step state lives in LangGraph checkpoints — recover
    via LangGraphWorkflowEngine.get_state, which falls back to the last
    valid checkpoint in the thread's history."""


class PostgresWorkflowRepository(WorkflowRepository):
    def __init__(self, database_url: str):
        self.database_url = database_url

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def upsert(self, workflow: AgentWorkflow) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO workflows (workflow_id, issue, status, classification)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (workflow_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    classification = COALESCE(EXCLUDED.classification,
                                              workflows.classification),
                    updated_at = now()
                """,
                (
                    workflow.workflow_id,
                    json.dumps(workflow.issue),
                    workflow.status.value,
                    workflow.classification,
                ),
            )

    def get(self, workflow_id: str) -> AgentWorkflow | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM workflows WHERE workflow_id = %s", (workflow_id,)
            ).fetchone()
        return self._to_aggregate(row) if row else None

    def list(self, status: str | None = None) -> list[AgentWorkflow]:
        query = "SELECT * FROM workflows"
        params: tuple = ()
        if status:
            query += " WHERE status = %s"
            params = (status,)
        query += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        workflows: list[AgentWorkflow] = []
        for row in rows:
            try:
                workflows.append(self._to_aggregate(row))
            except CorruptedWorkflowStateError:
                # One bad row must not blind the whole dashboard.
                logger.exception(
                    "Skipping corrupted workflow row %r", row.get("workflow_id")
                )
        return workflows

    @staticmethod
    def _to_aggregate(row: dict) -> AgentWorkflow:
        issue = row.get("issue")
        if not isinstance(issue, dict):
            raise CorruptedWorkflowStateError(
                f"Workflow {row.get('workflow_id')!r}: issue payload is "
                f"{type(issue).__name__}, expected object"
            )
        try:
            status = WorkflowStatus(row.get("status"))
        except ValueError as exc:
            raise CorruptedWorkflowStateError(
                f"Workflow {row.get('workflow_id')!r}: invalid status "
                f"{row.get('status')!r}"
            ) from exc
        return AgentWorkflow(
            workflow_id=row["workflow_id"],
            issue=issue,
            status=status,
            classification=row["classification"],
        )
