"""GitHubPRClient against a stubbed PyGithub repo — no network."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from github import GithubException

from pull_request.application.ports import PullRequestError, PullRequestGateway
from pull_request.domain.models import PullRequestDraft
from pull_request.infrastructure.github_pr_client import GitHubPRClient

DRAFT = PullRequestDraft(
    title="Fix #42: Login fails when email contains '+' character",
    body="Closes #42",
    branch="agentforge/issue-42",
    base="main",
    issue_number=42,
)


class StubRepo:
    def __init__(self, existing_files=None, fail_with=None):
        self.existing_files = existing_files or {}
        self.fail_with = fail_with
        self.created_refs = []
        self.created_files = []
        self.updated_files = []
        self.created_pulls = []

    def get_branch(self, name):
        return SimpleNamespace(name=name, commit=SimpleNamespace(sha="base-sha"))

    def create_git_ref(self, ref, sha):
        if self.fail_with:
            raise self.fail_with
        self.created_refs.append((ref, sha))

    def get_contents(self, path, ref):
        if path in self.existing_files:
            return SimpleNamespace(sha=self.existing_files[path])
        raise GithubException(404, {"message": "Not Found"}, {})

    def update_file(self, path, message, content, sha, branch):
        self.updated_files.append((path, content, sha, branch))

    def create_file(self, path, message, content, branch):
        self.created_files.append((path, content, branch))

    def create_pull(self, title, body, base, head):
        pull = SimpleNamespace(
            number=101,
            html_url="https://github.com/user/project/pull/101",
            title=title,
            body=body,
            base=base,
            head=head,
        )
        self.created_pulls.append(pull)
        return pull


class StubGithub:
    def __init__(self, repo):
        self.repo = repo
        self.requested = None

    def get_repo(self, full_name):
        self.requested = full_name
        return self.repo


def _client(repo) -> GitHubPRClient:
    return GitHubPRClient(repo_full_name="user/project", client=StubGithub(repo))


def test_client_implements_gateway_port():
    assert isinstance(_client(StubRepo()), PullRequestGateway)


def test_opens_pr_with_branch_commits_and_body():
    repo = StubRepo(existing_files={"src/auth/login.py": "old-sha"})
    client = _client(repo)

    pr = client.open_pull_request(
        DRAFT,
        changes={
            "src/auth/login.py": "updated content",   # existing -> update
            "tests/test_login_plus.py": "new test",   # missing  -> create
        },
    )

    # Branch created off the base branch head.
    assert repo.created_refs == [("refs/heads/agentforge/issue-42", "base-sha")]
    # Existing file updated with its blob sha; new file created.
    assert repo.updated_files == [
        ("src/auth/login.py", "updated content", "old-sha", "agentforge/issue-42")
    ]
    assert repo.created_files == [
        ("tests/test_login_plus.py", "new test", "agentforge/issue-42")
    ]
    # PR opened against base with the draft's title/body.
    opened = repo.created_pulls[0]
    assert opened.base == "main" and opened.head == "agentforge/issue-42"
    assert opened.body == "Closes #42"

    assert pr.number == 101
    assert pr.url.endswith("/pull/101")
    assert pr.issue_number == 42


def test_github_errors_are_wrapped():
    repo = StubRepo(fail_with=GithubException(422, {"message": "exists"}, {}))
    with pytest.raises(PullRequestError, match="issue #42"):
        _client(repo).open_pull_request(DRAFT, changes={})
