"""Use case: open a well-formed pull request for an approved fix (F-05).

The PR body must stand alone: a reviewer should not need to open the issue
to understand the change (U-05).
"""

from __future__ import annotations

from typing import Any

from ..domain.models import PullRequest, PullRequestDraft
from .ports import PullRequestGateway


class CreatePullRequestUseCase:
    def __init__(self, gateway: PullRequestGateway):
        self._gateway = gateway

    def execute(
        self,
        issue: dict[str, Any],
        analysis: dict[str, Any] | None,
        diffs: list[dict[str, Any]],
        changes: dict[str, str],
        test_summary: str = "",
        base: str = "main",
    ) -> PullRequest:
        number = int(issue.get("number", 0))
        draft = PullRequestDraft(
            title=f"Fix #{number}: {issue.get('title', '').strip()}",
            body=self._build_body(number, issue, analysis, diffs, test_summary),
            branch=f"agentforge/issue-{number}",
            base=base,
            issue_number=number,
        )
        return self._gateway.open_pull_request(draft, changes)

    @staticmethod
    def _build_body(
        number: int,
        issue: dict[str, Any],
        analysis: dict[str, Any] | None,
        diffs: list[dict[str, Any]],
        test_summary: str,
    ) -> str:
        sections = [f"Closes #{number}", "", "## Summary"]
        if analysis:
            sections.append(
                f"{analysis.get('symptoms', issue.get('title', ''))} "
                f"(severity: {analysis.get('severity', 'unknown')}, "
                f"area: {analysis.get('affected_area', 'unknown')})."
            )
            if analysis.get("reasoning"):
                sections.append(f"\n{analysis['reasoning']}")
        else:
            sections.append(issue.get("title", ""))

        sections.append("\n## Proposed changes")
        for diff in diffs:
            sections.append(f"\n`{diff.get('path', '?')}`\n")
            sections.append(f"```diff\n{diff.get('diff', '')}\n```")

        if test_summary:
            sections.append("\n## Test results")
            sections.append(test_summary)

        sections.append("\n---\n_Opened by AgentForge after human approval._")
        return "\n".join(sections)
