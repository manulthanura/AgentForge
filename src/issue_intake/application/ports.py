"""Ports (interfaces) the issue intake use cases depend on."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.models import Issue


class IssueReadError(RuntimeError):
    """Raised when an issue cannot be fetched from the source."""


class IssueReader(ABC):
    """Source of issues to analyze (GitHub in production)."""

    @abstractmethod
    def get_issue(self, number: int) -> Issue:
        """Fetch one issue by number. Raises IssueReadError on failure."""
