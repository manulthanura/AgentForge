"""Use case: draft a fix for a file and return it as a reviewable diff."""

from __future__ import annotations

from typing import Any

from ..domain.models import Diff
from ..domain.services import build_diff
from .ports import FixDrafter


class GenerateFixUseCase:
    def __init__(self, drafter: FixDrafter):
        self._drafter = drafter

    def execute(
        self,
        issue: dict[str, Any],
        analysis: dict[str, Any] | None,
        path: str,
        original: str,
        guidance: str = "",
    ) -> Diff:
        updated = self._drafter.draft(issue, analysis, path, original, guidance)
        return build_diff(path, original, updated)
