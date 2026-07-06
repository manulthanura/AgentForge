"""Ports (interfaces) the pull request use cases depend on."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.models import PullRequest, PullRequestDraft


class PullRequestError(RuntimeError):
    """Raised when the VCS host rejects a pull request operation."""


class PullRequestGateway(ABC):
    @abstractmethod
    def open_pull_request(
        self, draft: PullRequestDraft, changes: dict[str, str]
    ) -> PullRequest:
        """Create a branch, commit ``changes`` (path -> new content), and
        open a pull request. Raises PullRequestError on failure."""
