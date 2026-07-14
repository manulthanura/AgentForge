"""Diff building for proposed fixes — never touches disk."""

from __future__ import annotations

from fix_generation.application.propose_fix import ProposeFixUseCase
from fix_generation.domain.services import build_diff


def test_propose_fix_produces_unified_diff():
    diff = ProposeFixUseCase().execute(
        "src/login.py",
        original="email = raw\n",
        updated="email = sanitize(raw)\n",
    )
    assert diff.applied is False
    assert "-email = raw" in diff.content
    assert "+email = sanitize(raw)" in diff.content
    assert diff.to_dict() == {
        "path": "src/login.py",
        "diff": diff.content,
        "updated": "email = sanitize(raw)\n",
        "applied": False,
    }


def test_identical_content_yields_empty_diff():
    diff = build_diff("a.py", "same\n", "same\n")
    assert diff.is_empty
