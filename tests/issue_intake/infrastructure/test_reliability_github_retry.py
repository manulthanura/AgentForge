"""GitHub API outage/rate-limit recovery in the issue reader (R-03)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from github import GithubException

from issue_intake.application.ports import IssueReadError
from issue_intake.infrastructure.github_issue_reader import GitHubIssueReader
from pull_request.domain.models import PullRequestDraft
from pull_request.infrastructure.github_pr_client import GitHubPRClient


def _gh_issue():
    return SimpleNamespace(
        number=42, title="Login bug", body="steps", labels=[]
    )


class FlakyGithub:
    """get_repo succeeds; get_issue raises the queued errors, then works."""

    def __init__(self, failures):
        self.failures = list(failures)
        self.attempts = 0
        outer = self

        class _Repo:
            def get_issue(self, number):
                outer.attempts += 1
                if outer.failures:
                    raise outer.failures.pop(0)
                return _gh_issue()

        self._repo = _Repo()

    def get_repo(self, full_name):
        return self._repo


def _reader(client, sleeps) -> GitHubIssueReader:
    return GitHubIssueReader(
        repo_full_name="user/project", client=client, sleep=sleeps.append
    )


def test_github_503_outage_then_recovery():
    """Two 503s, then the API recovers — the issue is fetched."""
    sleeps: list[float] = []
    client = FlakyGithub(
        [
            GithubException(503, {"message": "unavailable"}, {}),
            GithubException(503, {"message": "unavailable"}, {}),
        ]
    )
    issue = _reader(client, sleeps).get_issue(42)
    assert issue.number == 42
    assert client.attempts == 3
    assert sleeps == [2.0, 4.0]


def test_github_rate_limit_respects_retry_after():
    sleeps: list[float] = []
    client = FlakyGithub(
        [GithubException(429, {"message": "rate limited"}, {"retry-after": "11"})]
    )
    issue = _reader(client, sleeps).get_issue(42)
    assert issue.number == 42
    assert sleeps == [11.0]


def test_github_404_is_not_retried():
    sleeps: list[float] = []
    client = FlakyGithub([GithubException(404, {"message": "Not Found"}, {})])
    with pytest.raises(IssueReadError):
        _reader(client, sleeps).get_issue(999)
    assert sleeps == []
    assert client.attempts == 1


def test_github_outage_exhausts_and_wraps():
    sleeps: list[float] = []
    client = FlakyGithub(
        [GithubException(503, {"message": "down"}, {}) for _ in range(10)]
    )
    with pytest.raises(IssueReadError):
        _reader(client, sleeps).get_issue(42)
    assert sleeps == [2.0, 4.0, 8.0]


# --- PR client -----------------------------------------------------------------


def test_pr_client_retries_transient_create_pull():
    sleeps: list[float] = []
    state = {"pull_attempts": 0}

    class _Repo:
        def get_branch(self, name):
            return SimpleNamespace(commit=SimpleNamespace(sha="sha"))

        def create_git_ref(self, ref, sha):
            pass

        def create_pull(self, title, body, base, head):
            state["pull_attempts"] += 1
            if state["pull_attempts"] < 2:
                raise GithubException(502, {"message": "bad gateway"}, {})
            return SimpleNamespace(number=7, html_url="https://x/pull/7")

    class _Client:
        def get_repo(self, name):
            return _Repo()

    client = GitHubPRClient(
        repo_full_name="user/project", client=_Client(), sleep=sleeps.append
    )
    draft = PullRequestDraft(
        title="t", body="b", branch="agentforge/issue-42", base="main",
        issue_number=42,
    )
    pr = client.open_pull_request(draft, changes={})
    assert pr.number == 7
    assert state["pull_attempts"] == 2
    assert sleeps == [2.0]
