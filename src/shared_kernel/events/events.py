"""Domain events shared across bounded contexts."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


@dataclass(frozen=True)
class DomainEvent:
    workflow_id: str
    occurred_at: str = field(default_factory=_now, kw_only=True)


@dataclass(frozen=True)
class IssueAnalyzed(DomainEvent):
    classification: str = "unknown"


@dataclass(frozen=True)
class ToolExecuted(DomainEvent):
    tool: str = ""
    ok: bool = True


@dataclass(frozen=True)
class WorkflowPaused(DomainEvent):
    reason: str = ""


@dataclass(frozen=True)
class WorkflowFinished(DomainEvent):
    status: str = "done"


@dataclass(frozen=True)
class WorkflowEscalated(DomainEvent):
    reason: str = ""


EventPayload = dict[str, Any]
