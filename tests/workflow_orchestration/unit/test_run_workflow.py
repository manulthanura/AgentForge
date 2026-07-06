"""RunWorkflowUseCase: repository index updates and event publishing."""

from __future__ import annotations

from shared_kernel.events import EventBus, WorkflowFinished
from workflow_orchestration.application.ports import (
    WorkflowEngine,
    WorkflowRepository,
)
from workflow_orchestration.application.run_workflow import RunWorkflowUseCase
from workflow_orchestration.domain.models import AgentWorkflow, WorkflowStatus


class FakeEngine(WorkflowEngine):
    def __init__(self, final_state):
        self.final_state = final_state
        self.calls = []
        self.resume_calls = []

    def run(self, initial_state, thread_id):
        self.calls.append((initial_state, thread_id))
        return {**initial_state, **self.final_state}

    def resume(self, decision, thread_id):
        self.resume_calls.append((decision, thread_id))
        return dict(self.final_state)


class InMemoryRepository(WorkflowRepository):
    def __init__(self):
        self.rows: dict[str, AgentWorkflow] = {}
        # Statuses captured at upsert time (the aggregate mutates in place).
        self.status_history: list[WorkflowStatus] = []

    def upsert(self, workflow):
        self.rows[workflow.workflow_id] = workflow
        self.status_history.append(workflow.status)

    def get(self, workflow_id):
        return self.rows.get(workflow_id)

    def list(self, status=None):
        return [
            w for w in self.rows.values()
            if status is None or w.status.value == status
        ]


def test_run_workflow_updates_index_and_publishes_event(sample_issue):
    engine = FakeEngine({"status": "done", "classification": "bug"})
    repository = InMemoryRepository()
    bus = EventBus()
    finished: list[WorkflowFinished] = []
    bus.subscribe(WorkflowFinished, finished.append)

    use_case = RunWorkflowUseCase(engine, repository, bus)
    final = use_case.execute("wf-42", sample_issue, workspace=".")

    assert final["status"] == "done"
    # Engine received the initial state under the workflow's thread id.
    (initial_state, thread_id) = engine.calls[0]
    assert thread_id == "wf-42"
    assert initial_state["status"] == WorkflowStatus.ANALYZING.value

    # Index row went through running -> final status.
    assert repository.status_history == [
        WorkflowStatus.ANALYZING,
        WorkflowStatus.DONE,
    ]
    assert repository.get("wf-42").status is WorkflowStatus.DONE
    assert repository.get("wf-42").classification == "bug"

    assert len(finished) == 1
    assert finished[0].status == "done"


def test_run_workflow_without_repository_or_bus(sample_issue):
    engine = FakeEngine({"status": "escalated"})
    final = RunWorkflowUseCase(engine).execute("wf-43", sample_issue)
    assert final["status"] == "escalated"
