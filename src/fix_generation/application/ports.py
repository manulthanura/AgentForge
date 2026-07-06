"""Ports (interfaces) the fix generation use cases depend on."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class FixDrafter(ABC):
    """Drafts the updated content of one file that fixes the analyzed issue."""

    @abstractmethod
    def draft(
        self,
        issue: dict[str, Any],
        analysis: dict[str, Any] | None,
        path: str,
        original: str,
        guidance: str = "",
    ) -> str:
        """Return the complete updated file content.

        Raises shared_kernel.llm.LLMError (or ValueError on unparseable
        output) — callers decide whether to retry or escalate.
        """
