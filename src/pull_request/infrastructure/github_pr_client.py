"""GitHub-backed PullRequestGateway using PyGithub."""

from __future__ import annotations

import time
from typing import Any, Callable

from github import Auth, Github, GithubException

from shared_kernel.resilience import RetryPolicy, retrying_github_call

from ..application.ports import PullRequestError, PullRequestGateway
from ..domain.models import PullRequest, PullRequestDraft


class GitHubPRClient(PullRequestGateway):
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

    def _call(self, fn: Callable[[], Any]) -> Any:
        """One GitHub interaction with 429/5xx backoff (R-03)."""
        return retrying_github_call(
            fn, policy=self._retry_policy, sleep=self._sleep
        )

    def open_pull_request(
        self, draft: PullRequestDraft, changes: dict[str, str]
    ) -> PullRequest:
        try:
            repo = self._call(lambda: self._client.get_repo(self._repo_full_name))
            base = self._call(lambda: repo.get_branch(draft.base))
            self._call(
                lambda: repo.create_git_ref(
                    ref=f"refs/heads/{draft.branch}", sha=base.commit.sha
                )
            )
            for path, content in changes.items():
                self._commit_file(repo, draft, path, content)
            pr = self._call(
                lambda: repo.create_pull(
                    title=draft.title,
                    body=draft.body,
                    base=draft.base,
                    head=draft.branch,
                )
            )
        except GithubException as exc:
            raise PullRequestError(
                f"Could not open PR for issue #{draft.issue_number} "
                f"on {self._repo_full_name}: {exc}"
            ) from exc
        return PullRequest(
            number=pr.number,
            url=pr.html_url,
            title=draft.title,
            branch=draft.branch,
            base=draft.base,
            issue_number=draft.issue_number,
        )

    @staticmethod
    def _commit_file(repo, draft: PullRequestDraft, path: str, content: str) -> None:
        message = f"Fix #{draft.issue_number}: update {path}"
        try:
            existing = repo.get_contents(path, ref=draft.branch)
            repo.update_file(
                path, message, content, existing.sha, branch=draft.branch
            )
        except GithubException as exc:
            if exc.status != 404:
                raise
            repo.create_file(path, message, content, branch=draft.branch)
