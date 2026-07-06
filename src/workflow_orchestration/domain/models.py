"""Workflow orchestration domain model."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class WorkflowStatus(StrEnum):
    ANALYZING = "analyzing"
    ROUTING = "routing"
    AWAITING_CLARIFICATION = "awaiting_clarification"
    AWAITING_APPROVAL = "awaiting_approval"  # used from Phase 3
    DONE = "done"
    ESCALATED = "escalated"

    @property
    def is_terminal(self) -> bool:
        return self in {
            WorkflowStatus.DONE,
            WorkflowStatus.ESCALATED,
            WorkflowStatus.AWAITING_CLARIFICATION,
        }


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclass(frozen=True)
class Decision:
    """One logged agent decision — the transparency record."""

    node: str
    action: str
    reasoning: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": self.node,
            "action": self.action,
            "reasoning": self.reasoning,
            "args": self.args,
            "at": self.at,
        }


@dataclass
class AgentWorkflow:
    """The workflow aggregate as persisted in the index table.

    Step-by-step runtime state lives in LangGraph checkpoints; this is the
    queryable identity + status view.
    """

    workflow_id: str
    issue: dict[str, Any]
    status: WorkflowStatus = WorkflowStatus.ANALYZING
    classification: str | None = None
