"""GitHub-backed IssueReader using PyGithub."""

from __future__ import annotations

import time
from typing import Callable

from github import Auth, Github, GithubException

from shared_kernel.resilience import RetryPolicy, retrying_github_call

from ..application.ports import IssueReader, IssueReadError
from ..domain.models import Issue


class GitHubIssueReader(IssueReader):
    def __init__(
        self,
        repo_full_name: str,
        token: str | None = None,
        client: Github | None = None,
        retry_policy: RetryPolicy | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        """``client`` injection is for tests; production passes a token."""
        if client is None:
            auth = Auth.Token(token) if token else None
            client = Github(auth=auth)
        self._client = client
        self._repo_full_name = repo_full_name
        self._retry_policy = retry_policy
        self._sleep = sleep

    def get_issue(self, number: int) -> Issue:
        def _fetch():
            repo = self._client.get_repo(self._repo_full_name)
            return repo.get_issue(number=number)

        try:
            # Transient GitHub failures (429/5xx) back off and retry (R-03).
            gh_issue = retrying_github_call(
                _fetch, policy=self._retry_policy, sleep=self._sleep
            )
        except GithubException as exc:
            raise IssueReadError(
                f"Could not read issue #{number} from {self._repo_full_name}: {exc}"
            ) from exc
        return Issue(
            number=gh_issue.number,
            title=gh_issue.title or "",
            body=gh_issue.body or "",
            labels=tuple(label.name for label in gh_issue.labels),
        )
