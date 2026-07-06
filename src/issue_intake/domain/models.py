"""Issue intake domain model — pure, no framework or SDK imports."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class IssueType(StrEnum):
    BUG = "bug"
    FEATURE_REQUEST = "feature_request"
    QUESTION = "question"
    INSUFFICIENT_INFORMATION = "insufficient_information"
    UNKNOWN = "unknown"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class Issue:
    number: int
    title: str
    body: str
    labels: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Issue:
        return cls(
            number=int(data.get("number", 0)),
            title=str(data.get("title", "")),
            body=str(data.get("body", "")),
            labels=tuple(data.get("labels", ())),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "title": self.title,
            "body": self.body,
            "labels": list(self.labels),
        }


@dataclass(frozen=True)
class IssueAnalysis:
    issue_type: IssueType
    affected_area: str
    symptoms: str
    severity: Severity
    reasoning: str

    @property
    def needs_clarification(self) -> bool:
        return self.issue_type is IssueType.INSUFFICIENT_INFORMATION

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> IssueAnalysis:
        """Build from an untrusted dict (LLM output), falling back safely."""
        try:
            issue_type = IssueType(str(payload.get("issue_type", "")).lower())
        except ValueError:
            issue_type = IssueType.UNKNOWN
        try:
            severity = Severity(str(payload.get("severity", "")).lower())
        except ValueError:
            severity = Severity.MEDIUM
        return cls(
            issue_type=issue_type,
            affected_area=str(payload.get("affected_area", "unknown")),
            symptoms=str(payload.get("symptoms", "")),
            severity=severity,
            reasoning=str(payload.get("reasoning", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "issue_type": self.issue_type.value,
            "affected_area": self.affected_area,
            "symptoms": self.symptoms,
            "severity": self.severity.value,
            "reasoning": self.reasoning,
        }
