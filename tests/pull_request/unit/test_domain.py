from pull_request.domain.models import PullRequestDraft


def test_draft_holds_pr_fields():
    draft = PullRequestDraft(
        title="Fix login for emails containing '+'",
        body="Closes #42",
        branch="agent/fix-42",
        base="main",
        issue_number=42,
    )
    assert draft.issue_number == 42
    assert draft.base == "main"
