"""Approval domain model."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field, replace
from enum import StrEnum


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


@dataclass(frozen=True)
class ApprovalGate:
    """An action that requires human sign-off before execution."""

    action: str  # e.g. "create_pull_request", "push_code"
    timeout_hours: int = 72

    def is_irreversible(self) -> bool:
        # Every gated action is treated as irreversible by definition.
        return True


@dataclass(frozen=True)
class ApprovalRequest:
    """One pending human decision for one workflow."""

    workflow_id: str
    action: str
    status: ApprovalStatus = ApprovalStatus.PENDING
    feedback: str = ""
    requested_at: datetime.datetime = field(default_factory=_now)
    decided_at: datetime.datetime | None = None
    reminded_at: datetime.datetime | None = None

    def decide(self, approved: bool, feedback: str = "") -> ApprovalRequest:
        return replace(
            self,
            status=ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED,
            feedback=feedback,
            decided_at=_now(),
        )

    def time_out(self) -> ApprovalRequest:
        return replace(self, status=ApprovalStatus.TIMED_OUT, decided_at=_now())

    def with_reminder(self, at: datetime.datetime) -> ApprovalRequest:
        return replace(self, reminded_at=at)

    def age_hours(self, now: datetime.datetime | None = None) -> float:
        current = now or _now()
        return (current - self.requested_at).total_seconds() / 3600
