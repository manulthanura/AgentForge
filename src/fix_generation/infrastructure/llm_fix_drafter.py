"""LLM-backed FixDrafter using the shared-kernel LLM port."""

from __future__ import annotations

import json
from typing import Any

from shared_kernel.llm import LLMProvider

from ..application.ports import FixDrafter

DRAFT_SYSTEM = """\
You are AgentForge's fix drafter. Given a GitHub issue, its analysis, and the
current content of one file, produce the complete updated content of that
file with the minimal change that fixes the issue.

Rules:
- Modify only what the root cause requires; preserve function signatures.
- Match the file's existing style and conventions.
- Add a short inline comment only where the change needs explanation.
- Never include secrets, credentials, or new dependencies.

Respond with JSON:
{"updated_content": "<the full new file content>",
 "explanation": "<one or two sentences on what changed and why>"}
"""


class LLMFixDrafter(FixDrafter):
    def __init__(self, provider: LLMProvider, max_tokens: int = 8192):
        self._provider = provider
        self._max_tokens = max_tokens

    def draft(
        self,
        issue: dict[str, Any],
        analysis: dict[str, Any] | None,
        path: str,
        original: str,
        guidance: str = "",
    ) -> str:
        user = json.dumps(
            {
                "issue": issue,
                "analysis": analysis,
                "file_path": path,
                "current_content": original,
                "extra_guidance": guidance,
            },
            default=str,
        )
        payload = self._provider.complete_json(
            [{"role": "user", "content": user}],
            system=DRAFT_SYSTEM,
            max_tokens=self._max_tokens,
        )
        updated = payload.get("updated_content")
        if not isinstance(updated, str) or not updated:
            raise ValueError(
                f"Fix drafter returned no updated_content for {path!r}"
            )
        return updated
