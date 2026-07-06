"""PostgreSQL implementation of the ApprovalRepository port."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from ..application.ports import ApprovalRepository
from ..domain.models import ApprovalRequest, ApprovalStatus


class PostgresApprovalRepository(ApprovalRepository):
    def __init__(self, database_url: str):
        self.database_url = database_url

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def save(self, request: ApprovalRequest) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO approvals
                    (workflow_id, action, status, feedback,
                     requested_at, decided_at, reminded_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (workflow_id) DO UPDATE SET
                    status = EXCLUDED.status,
                    feedback = EXCLUDED.feedback,
                    decided_at = EXCLUDED.decided_at,
                    reminded_at = EXCLUDED.reminded_at
                """,
                (
                    request.workflow_id,
                    request.action,
                    request.status.value,
                    request.feedback,
                    request.requested_at,
                    request.decided_at,
                    request.reminded_at,
                ),
            )

    def get(self, workflow_id: str) -> ApprovalRequest | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM approvals WHERE workflow_id = %s", (workflow_id,)
            ).fetchone()
        return self._to_domain(row) if row else None

    def list_pending(self) -> list[ApprovalRequest]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM approvals WHERE status = %s ORDER BY requested_at",
                (ApprovalStatus.PENDING.value,),
            ).fetchall()
        return [self._to_domain(row) for row in rows]

    @staticmethod
    def _to_domain(row: dict) -> ApprovalRequest:
        return ApprovalRequest(
            workflow_id=row["workflow_id"],
            action=row["action"],
            status=ApprovalStatus(row["status"]),
            feedback=row["feedback"] or "",
            requested_at=row["requested_at"],
            decided_at=row["decided_at"],
            reminded_at=row["reminded_at"],
        )
