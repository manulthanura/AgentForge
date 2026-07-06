"""Use case: run a workflow for an incoming issue.

ResumeWorkflowUseCase (approval-gated continuation) arrives with Phase 3;
it will re-enter the same engine from its checkpoint.
"""

from __future__ import annotations

from typing import Any

from shared_kernel.events import EventBus, WorkflowFinished, WorkflowPaused

from ..domain.models import AgentWorkflow, WorkflowStatus
from .ports import WorkflowEngine, WorkflowRepository


class RunWorkflowUseCase:
    def __init__(
        self,
        engine: WorkflowEngine,
        repository: WorkflowRepository | None = None,
        event_bus: EventBus | None = None,
    ):
        self._engine = engine
        self._repository = repository
        self._event_bus = event_bus

    def execute(
        self, workflow_id: str, issue: dict[str, Any], workspace: str = "."
    ) -> dict[str, Any]:
        workflow = AgentWorkflow(workflow_id=workflow_id, issue=issue)
        if self._repository:
            self._repository.upsert(workflow)

        initial_state = {
            "workflow_id": workflow_id,
            "issue": issue,
            "workspace": workspace,
            "status": WorkflowStatus.ANALYZING.value,
            "step_count": 0,
        }
        final_state = self._engine.run(initial_state, thread_id=workflow_id)

        status = final_state.get("status", WorkflowStatus.ESCALATED.value)
        workflow.status = WorkflowStatus(status)
        workflow.classification = final_state.get("classification")
        if self._repository:
            self._repository.upsert(workflow)
        if self._event_bus:
            if status == WorkflowStatus.AWAITING_APPROVAL.value:
                # Paused at the gate; WorkflowFinished comes after resume.
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
