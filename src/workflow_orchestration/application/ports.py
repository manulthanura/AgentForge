"""Ports the orchestration use cases depend on."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..domain.models import AgentWorkflow


class WorkflowRepository(ABC):
    """Index of workflows for dashboards, dedupe, and metrics."""

    @abstractmethod
    def upsert(self, workflow: AgentWorkflow) -> None: ...

    @abstractmethod
    def get(self, workflow_id: str) -> AgentWorkflow | None: ...

    @abstractmethod
    def list(self, status: str | None = None) -> list[AgentWorkflow]: ...


class WorkflowEngine(ABC):
    """Runs a workflow's state machine to completion (or a pause point)."""

    @abstractmethod
    def run(self, initial_state: dict[str, Any], thread_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def resume(self, decision: dict[str, Any], thread_id: str) -> dict[str, Any]:
        """Continue a paused workflow from its checkpoint with a decision."""
