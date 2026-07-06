"""CreatePullRequestUseCase: well-formed PRs per F-05 / U-05."""

from __future__ import annotations

from pull_request.application.create_pull_request import CreatePullRequestUseCase
from pull_request.application.ports import PullRequestGateway
from pull_request.domain.models import PullRequest


class RecordingGateway(PullRequestGateway):
    def __init__(self):
        self.draft = None
        self.changes = None

    def open_pull_request(self, draft, changes):
        self.draft = draft
        self.changes = changes
        return PullRequest(
            number=101,
            url="https://github.com/user/project/pull/101",
            title=draft.title,
            branch=draft.branch,
            base=draft.base,
            issue_number=draft.issue_number,
        )


def test_pr_contains_title_link_diff_and_tests(sample_issue):
    gateway = RecordingGateway()
    use_case = CreatePullRequestUseCase(gateway)
    analysis = {
        "issue_type": "bug",
        "affected_area": "authentication",
        "symptoms": "login failure with special characters",
        "severity": "high",
        "reasoning": "Email sanitization strips '+' from addresses.",
    }
    diffs = [
        {"path": "src/auth/login.py", "diff": "-return email\n+return sanitize(email)"}
    ]

    pr = use_case.execute(
        issue=sample_issue,
        analysis=analysis,
        diffs=diffs,
        changes={"src/auth/login.py": "new content"},
        test_summary="5 passed, 0 failed (sandbox run 2026-07-04)",
    )

    draft = gateway.draft
    # Descriptive title referencing the issue (F-05).
    assert draft.title == f"Fix #42: {sample_issue['title']}"
    # Linked issue.
    assert "Closes #42" in draft.body
    # Diff included as a reviewable block.
    assert "```diff" in draft.body
    assert "+return sanitize(email)" in draft.body
    assert "src/auth/login.py" in draft.body
    # Test results included.
    assert "5 passed" in draft.body
    # Standalone summary (U-05): reviewer sees symptoms without opening the issue.
    assert "login failure with special characters" in draft.body

    assert draft.branch == "agentforge/issue-42"
    assert gateway.changes == {"src/auth/login.py": "new content"}
    assert pr.number == 101
    assert pr.url.endswith("/pull/101")


def test_pr_body_without_analysis_or_tests_still_standalone(sample_issue):
    gateway = RecordingGateway()
    CreatePullRequestUseCase(gateway).execute(
        issue=sample_issue, analysis=None, diffs=[], changes={}
    )
    assert sample_issue["title"] in gateway.draft.body
    assert "Closes #42" in gateway.draft.body
    assert "Test results" not in gateway.draft.body
