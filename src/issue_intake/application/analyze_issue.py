"""Use case: analyze a GitHub issue and classify it."""

from __future__ import annotations

from shared_kernel.llm import LLMProvider

from ..domain.models import Issue, IssueAnalysis

ANALYZE_SYSTEM = """\
You analyze GitHub issues for an autonomous fixing agent. Classify the issue
and extract structured data. If the issue lacks enough information to act on
(no reproduction steps, no concrete symptom, e.g. just "it doesn't work"),
classify it as insufficient_information.

Respond with JSON:
{"issue_type": "bug" | "feature_request" | "insufficient_information" | "question",
 "affected_area": "<subsystem or unknown>",
 "symptoms": "<short summary>",
 "severity": "low" | "medium" | "high",
 "reasoning": "<why>"}
"""


class AnalyzeIssueUseCase:
    def __init__(self, llm: LLMProvider):
        self._llm = llm

    def execute(self, issue: Issue) -> IssueAnalysis:
        """Classify the issue. Raises LLMError/ValueError on provider failure."""
        user = (
            f"Issue #{issue.number}: {issue.title}\n\n"
            f"{issue.body}\n\nLabels: {list(issue.labels)}"
        )
        payload = self._llm.complete_json(
            [{"role": "user", "content": user}], system=ANALYZE_SYSTEM
        )
        return IssueAnalysis.from_payload(payload)
