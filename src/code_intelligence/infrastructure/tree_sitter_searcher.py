"""AST-aware code searcher backed by tree-sitter, with relevance ranking.

Scoring model (per F-02: return relevant files ranked by relevance):
- query term matches a function/class definition name ..... +10
- query term appears in the file path ..................... +5
- query term appears on any other line .................... +1 per line

Python files are parsed with tree-sitter to find definitions; other file
types fall back to plain line scanning (still scored and ranked). Use
FilesystemCodeSearcher for a dependency-free local-dev fallback.
"""

from __future__ import annotations

import re
from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from ..application.ports import CodeSearcher
from ..domain.models import CodeLocation, CodeSearchResult, FileRelevance

_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"}

_DEFINITION_SCORE = 10.0
_PATH_SCORE = 5.0
_LINE_SCORE = 1.0
_LOCATIONS_PER_FILE = 5


def _terms(query: str) -> list[str]:
    """Split a free-form query into lowercase search terms."""
    return [t for t in re.split(r"[^a-zA-Z0-9_]+", query.lower()) if len(t) >= 3]


class TreeSitterCodeSearcher(CodeSearcher):
    def __init__(self) -> None:
        self._parser = Parser(Language(tspython.language()))

    def search(
        self, query: str, workspace: str | Path, max_results: int = 20
    ) -> CodeSearchResult:
        root = Path(workspace)
        if not root.is_dir():
            return CodeSearchResult(query=query, error=f"workspace {root} not found")
        terms = _terms(query) or [query.lower()]

        scored: list[tuple[float, str, list[CodeLocation]]] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or set(path.parts) & _SKIP_DIRS:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            rel_path = str(path.relative_to(root))
            score, locations = self._score_file(rel_path, text, terms)
            if score > 0:
                scored.append((score, rel_path, locations))

        scored.sort(key=lambda item: (-item[0], item[1]))

        ranked = tuple(FileRelevance(file=f, score=s) for s, f, _ in scored)
        matches: list[CodeLocation] = []
        truncated = False
        for _, _, locations in scored:
            for location in locations:
                if len(matches) >= max_results:
                    truncated = True
                    break
                matches.append(location)
            if truncated:
                break

        return CodeSearchResult(
            query=query,
            matches=tuple(matches),
            ranked_files=ranked,
            truncated=truncated,
        )

    def _score_file(
        self, rel_path: str, text: str, terms: list[str]
    ) -> tuple[float, list[CodeLocation]]:
        lines = text.splitlines()
        score = 0.0
        locations: list[CodeLocation] = []

        path_lower = rel_path.lower()
        score += sum(_PATH_SCORE for t in terms if t in path_lower)

        definition_lines: set[int] = set()
        if rel_path.endswith(".py"):
            for name, line in self._definitions(text):
                if any(t in name.lower() for t in terms):
                    score += _DEFINITION_SCORE
                    definition_lines.add(line)
                    locations.append(
                        CodeLocation(
                            file=rel_path,
                            line=line,
                            text=lines[line - 1].strip()[:200],
                        )
                    )

        for lineno, line in enumerate(lines, start=1):
            if lineno in definition_lines:
                continue
            line_lower = line.lower()
            if any(t in line_lower for t in terms):
                score += _LINE_SCORE
                if len(locations) < _LOCATIONS_PER_FILE:
                    locations.append(
                        CodeLocation(
                            file=rel_path, line=lineno, text=line.strip()[:200]
                        )
                    )

        return score, locations[:_LOCATIONS_PER_FILE]

    def _definitions(self, text: str) -> list[tuple[str, int]]:
        """Extract (name, 1-based line) for function/class definitions."""
        tree = self._parser.parse(text.encode("utf-8"))
        found: list[tuple[str, int]] = []

        def walk(node: Node) -> None:
            if node.type in ("function_definition", "class_definition"):
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    found.append(
                        (name_node.text.decode("utf-8"), node.start_point[0] + 1)
                    )
            for child in node.children:
                walk(child)

        walk(tree.root_node)
        return found
