"""Ports (interfaces) the approval use cases depend on."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..domain.models import ApprovalRequest


class ApprovalRepository(ABC):
    @abstractmethod
    def save(self, request: ApprovalRequest) -> None: ...

    @abstractmethod
    def get(self, workflow_id: str) -> ApprovalRequest | None: ...

    @abstractmethod
    def list_pending(self) -> list[ApprovalRequest]: ...


class WorkflowResumer(ABC):
    """Resumes a paused workflow with a human decision.

    Implemented by workflow_orchestration's ResumeWorkflowUseCase; the port
    keeps this context from importing another context's internals.
    """

    @abstractmethod
    def execute(self, workflow_id: str, decision: dict[str, Any]) -> dict[str, Any]: ...
