"""Pull request domain model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PullRequestDraft:
    title: str
    body: str
    branch: str
    base: str
    issue_number: int


@dataclass(frozen=True)
class PullRequest:
    """A pull request that exists on the VCS host."""

    number: int
    url: str
    title: str
    branch: str
    base: str
    issue_number: int
