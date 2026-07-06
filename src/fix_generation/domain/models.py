"""Fix generation domain model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Diff:
    """A proposed change to one file, as a unified diff.

    ``applied`` is always False in this context: applying changes is gated
    behind human approval (approval context, Phase 3).
    """

    path: str
    content: str
    applied: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.content.strip()

    def to_dict(self) -> dict[str, Any]:
        return {"path": self.path, "diff": self.content, "applied": self.applied}
