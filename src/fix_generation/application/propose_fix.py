"""Use case: turn a proposed file edit into a reviewable diff.

Phase 1 receives the updated content from the caller (the agent router
supplies it); LLM-backed fix drafting arrives with Phase 2 and will live in
this context's infrastructure layer behind a port.
"""

from __future__ import annotations

from ..domain.models import Diff
from ..domain.services import build_diff


class ProposeFixUseCase:
    def execute(self, path: str, original: str, updated: str) -> Diff:
        return build_diff(path, original, updated)
