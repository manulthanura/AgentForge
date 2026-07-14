"""Pure domain services for fix generation."""

from __future__ import annotations

import difflib

from .models import Diff


def build_diff(path: str, original: str, updated: str) -> Diff:
    """Produce a unified diff for a proposed file edit. Nothing touches disk."""
    content = "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )
    return Diff(path=path, content=content, updated=updated)
