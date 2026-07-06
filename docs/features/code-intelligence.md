# Code Intelligence

Finding the code an issue is about, ranked by relevance (F-02), behind one
port: `CodeSearcher.search(query, workspace, max_results) -> CodeSearchResult`.

## Searchers

| Adapter | How it works | When |
|---------|-------------|------|
| `TreeSitterCodeSearcher` | parses Python files into ASTs, scores definition-name hits highest | primary (default) |
| `FilesystemCodeSearcher` | regex/substring line scan, dependency-free | fallback + `CODE_SEARCHER=filesystem` |
| `FallbackCodeSearcher` | tries primary, degrades to fallback on any exception (R-09) | what the bootstrap actually wires |

## Relevance scoring (tree-sitter)

Per file, per query term:

| Signal | Score |
|--------|-------|
| term matches a `def`/`class` name (AST) | +10 |
| term appears in the file path | +5 |
| term appears on any other line | +1 per line |

Results carry both flat `matches` (capped at `max_results`, ordered by file
rank, definition lines first) and `ranked_files` — every relevant file with
its score, most relevant first, even when matches truncate. Non-Python
files fall back to line scanning so they still participate in ranking.

Example: searching `validate_email` in the F-02 fixture ranks
`src/auth/login.py` (defines it, 10+) above `src/utils/validators.py`
(imports it, 1) above `tests/test_auth.py` (references it, 1) — and
excludes unrelated files entirely.

## Degradation path

1. Tree-sitter raises (grammar crash, encoding edge case) →
   `FallbackCodeSearcher` logs and reruns the query on the filesystem
   scanner; `fallback_count` increments for observability.
2. Both engines raise → the exception propagates to the workflow's
   `execute_tool`, which records a failed tool result.
3. Three consecutive failed tools trip the compound-failure guard and the
   workflow escalates to a human instead of retrying forever (R-09).

## Query handling details

- Queries are split into lowercase terms (≥3 chars); an invalid regex in
  the filesystem scanner degrades to a literal substring match.
- `.git`, `.venv`, `node_modules`, `__pycache__`, `.pytest_cache` are
  always skipped; unreadable/binary files are ignored.
- A missing workspace returns `CodeSearchResult(error=...)` rather than
  raising — "no relevant code found" is a normal outcome the router can
  reason about.
