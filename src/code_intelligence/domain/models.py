"""Code intelligence domain model — pure values, no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CodeLocation:
    file: str
    line: int
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "line": self.line, "text": self.text}


@dataclass(frozen=True)
class FileRelevance:
    """A file's aggregated relevance to a query (higher score = more relevant)."""

    file: str
    score: float

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "score": self.score}


@dataclass(frozen=True)
class CodeSearchResult:
    query: str
    matches: tuple[CodeLocation, ...] = ()
    # Files ordered most-relevant first; empty for searchers that don't rank.
    ranked_files: tuple[FileRelevance, ...] = ()
    truncated: bool = False
    error: str | None = None

    @property
    def found(self) -> bool:
        return bool(self.matches)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "query": self.query,
            "matches": [m.to_dict() for m in self.matches],
            "truncated": self.truncated,
        }
        if self.ranked_files:
            result["ranked_files"] = [f.to_dict() for f in self.ranked_files]
        if self.error:
            result["error"] = self.error
        return result
