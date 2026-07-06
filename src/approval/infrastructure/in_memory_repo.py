"""In-memory ApprovalRepository for local/demo mode and tests."""

from __future__ import annotations

from ..application.ports import ApprovalRepository
from ..domain.models import ApprovalRequest, ApprovalStatus


class InMemoryApprovalRepository(ApprovalRepository):
    def __init__(self) -> None:
        self._requests: dict[str, ApprovalRequest] = {}

    def save(self, request: ApprovalRequest) -> None:
        self._requests[request.workflow_id] = request

    def get(self, workflow_id: str) -> ApprovalRequest | None:
        return self._requests.get(workflow_id)

    def list_pending(self) -> list[ApprovalRequest]:
        return [
            r
            for r in self._requests.values()
            if r.status is ApprovalStatus.PENDING
        ]
