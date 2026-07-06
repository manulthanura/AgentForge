"""Regex/substring search over a local checkout.

TreeSitterParser and GitHubCodeSearchClient arrive with Phase 2.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..application.ports import CodeSearcher
from ..domain.models import CodeLocation, CodeSearchResult

_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}


class FilesystemCodeSearcher(CodeSearcher):
    def search(
        self, query: str, workspace: str | Path, max_results: int = 20
    ) -> CodeSearchResult:
        root = Path(workspace)
        if not root.is_dir():
            return CodeSearchResult(
                query=query, error=f"workspace {root} not found"
            )
        try:
            pattern = re.compile(query, re.IGNORECASE)
        except re.error:
            pattern = re.compile(re.escape(query), re.IGNORECASE)

        matches: list[CodeLocation] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or set(path.parts) & _SKIP_DIRS:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    matches.append(
                        CodeLocation(
                            file=str(path.relative_to(root)),
                            line=lineno,
                            text=line.strip()[:200],
                        )
                    )
                    if len(matches) >= max_results:
                        return CodeSearchResult(
                            query=query, matches=tuple(matches), truncated=True
                        )
        return CodeSearchResult(query=query, matches=tuple(matches))
