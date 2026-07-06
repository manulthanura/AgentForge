"""Issue analysis use case and domain parsing."""

from __future__ import annotations

import json

import pytest

from issue_intake.application.analyze_issue import AnalyzeIssueUseCase
from issue_intake.domain.models import Issue, IssueAnalysis, IssueType, Severity
from shared_kernel.llm import LLMError

from tests.support.fakes import FailingProvider, FakeProvider


def test_analyze_bug_issue(sample_issue):
    provider = FakeProvider(
        responses=[
            json.dumps(
                {
                    "issue_type": "bug",
                    "affected_area": "authentication",
                    "symptoms": "login failure with special characters",
                    "severity": "high",
                    "reasoning": "Repro steps point at email validation.",
                }
            )
        ]
    )
    analysis = AnalyzeIssueUseCase(provider).execute(Issue.from_dict(sample_issue))

    assert analysis.issue_type is IssueType.BUG
    assert analysis.affected_area == "authentication"
    assert analysis.severity is Severity.HIGH
    assert not analysis.needs_clarification
    # The prompt carried the issue content.
    assert "'+'" in provider.calls[0]["messages"][0]["content"]


def test_vague_issue_needs_clarification(vague_issue):
    provider = FakeProvider(
        responses=[
            json.dumps(
                {
                    "issue_type": "insufficient_information",
                    "affected_area": "unknown",
                    "symptoms": "unspecified",
                    "severity": "low",
                    "reasoning": "No reproduction steps.",
                }
            )
        ]
    )
    analysis = AnalyzeIssueUseCase(provider).execute(Issue.from_dict(vague_issue))
    assert analysis.needs_clarification


def test_provider_outage_propagates(sample_issue):
    with pytest.raises(LLMError):
        AnalyzeIssueUseCase(FailingProvider()).execute(Issue.from_dict(sample_issue))


def test_analysis_from_payload_tolerates_bad_enums():
    analysis = IssueAnalysis.from_payload(
        {"issue_type": "weird", "severity": "catastrophic"}
    )
    assert analysis.issue_type is IssueType.UNKNOWN
    assert analysis.severity is Severity.MEDIUM  # safe default


def test_issue_dict_roundtrip(sample_issue):
    issue = Issue.from_dict(sample_issue)
    assert issue.number == 42
    assert issue.to_dict() == sample_issue
