"""Use case: apply a human approval decision and resume the workflow."""

from __future__ import annotations

from typing import Any

from ..domain.models import ApprovalStatus
from .ports import ApprovalRepository, WorkflowResumer


class UnknownApprovalError(LookupError):
    """The referenced workflow has no pending approval request."""


class HandleApprovalResponseUseCase:
    def __init__(
        self,
        resumer: WorkflowResumer,
        repository: ApprovalRepository | None = None,
    ):
        self._resumer = resumer
        self._repository = repository

    def execute(
        self, workflow_id: str, approved: bool, feedback: str = ""
    ) -> dict[str, Any]:
        if self._repository:
            request = self._repository.get(workflow_id)
            if request is None:
                raise UnknownApprovalError(
                    f"No approval request for workflow {workflow_id!r}"
                )
            if request.status is not ApprovalStatus.PENDING:
                raise UnknownApprovalError(
                    f"Approval for {workflow_id!r} already {request.status.value}"
                )
            self._repository.save(request.decide(approved, feedback))

        return self._resumer.execute(
            workflow_id, {"approved": approved, "feedback": feedback}
        )
