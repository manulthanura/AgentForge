"""Use case: resume a paused workflow from its checkpoint (F-07).

Implements the approval context's WorkflowResumer port so an approval event
can wake the exact workflow that paused, with its full state intact.
"""

from __future__ import annotations

from typing import Any

from approval.application.ports import WorkflowResumer
from shared_kernel.events import EventBus, WorkflowFinished, WorkflowPaused

from ..domain.models import AgentWorkflow, WorkflowStatus
from .ports import WorkflowEngine, WorkflowRepository


class ResumeWorkflowUseCase(WorkflowResumer):
    def __init__(
        self,
        engine: WorkflowEngine,
        repository: WorkflowRepository | None = None,
        event_bus: EventBus | None = None,
    ):
        self._engine = engine
        self._repository = repository
        self._event_bus = event_bus

    def execute(self, workflow_id: str, decision: dict[str, Any]) -> dict[str, Any]:
        final_state = self._engine.resume(decision, thread_id=workflow_id)
        status = final_state.get("status", WorkflowStatus.ESCALATED.value)

        if self._repository:
            self._repository.upsert(
                AgentWorkflow(
                    workflow_id=workflow_id,
                    issue=final_state.get("issue", {}),
                    status=WorkflowStatus(status),
                    classification=final_state.get("classification"),
                )
            )
        if self._event_bus:
            if status == WorkflowStatus.AWAITING_APPROVAL.value:
                # Rejected and re-worked; paused again at the gate.
                self._event_bus.publish(
                    WorkflowPaused(
                        workflow_id=workflow_id, reason="awaiting_approval"
                    )
                )
            else:
                self._event_bus.publish(
                    WorkflowFinished(workflow_id=workflow_id, status=status)
                )
        return final_state
