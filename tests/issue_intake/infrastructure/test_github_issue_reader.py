"""GitHubIssueReader against a stubbed PyGithub client — no network."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from github import GithubException

from issue_intake.application.ports import IssueReader, IssueReadError
from issue_intake.domain.models import Issue
from issue_intake.infrastructure.github_issue_reader import GitHubIssueReader


class StubGithub:
    def __init__(self, issue=None, error=None):
        self.issue = issue
        self.error = error
        self.requested_repo = None
        self.requested_number = None

    def get_repo(self, full_name):
        self.requested_repo = full_name
        outer = self

        class _Repo:
            def get_issue(self, number):
                outer.requested_number = number
                if outer.error:
                    raise outer.error
                return outer.issue

        return _Repo()


def _gh_issue():
    return SimpleNamespace(
        number=42,
        title="Login fails when email contains '+' character",
        body="Steps to reproduce: ...",
        labels=[SimpleNamespace(name="bug"), SimpleNamespace(name="auth")],
    )


def test_reader_implements_port_and_maps_domain_issue():
    stub = StubGithub(issue=_gh_issue())
    reader = GitHubIssueReader(repo_full_name="user/project", client=stub)
    assert isinstance(reader, IssueReader)

    issue = reader.get_issue(42)

    assert stub.requested_repo == "user/project"
    assert stub.requested_number == 42
    assert isinstance(issue, Issue)
    assert issue.number == 42
    assert "'+'" in issue.title
    assert issue.labels == ("bug", "auth")


def test_reader_handles_null_body_and_no_labels():
    gh_issue = SimpleNamespace(number=7, title="t", body=None, labels=[])
    reader = GitHubIssueReader(
        repo_full_name="user/project", client=StubGithub(issue=gh_issue)
    )
    issue = reader.get_issue(7)
    assert issue.body == ""
    assert issue.labels == ()


def test_reader_wraps_github_errors():
    error = GithubException(404, {"message": "Not Found"}, {})
    reader = GitHubIssueReader(
        repo_full_name="user/project", client=StubGithub(error=error)
    )
    with pytest.raises(IssueReadError, match="issue #99"):
        reader.get_issue(99)
