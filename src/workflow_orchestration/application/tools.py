"""Agent tool catalog.

Tools are named actions the router can choose. Their handlers delegate to
other bounded contexts' use cases — this module wires capability names to
capabilities, it contains no business logic of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from code_intelligence.application.search_relevant_code import (
    SearchRelevantCodeUseCase,
)
from fix_generation.application.generate_fix import GenerateFixUseCase
from fix_generation.application.propose_fix import ProposeFixUseCase
from issue_intake.domain.models import Issue

ToolHandler = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_schema: dict[str, str]  # arg name -> human description
    handler: ToolHandler


class ToolCatalog:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            raise ValueError(f"Tool {spec.name!r} already registered")
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(f"Unknown tool {name!r}") from None

    def names(self) -> list[str]:
        return list(self._tools)

    def describe(self) -> str:
        """Render the tool catalog for the router prompt."""
        lines = []
        for spec in self._tools.values():
            args = ", ".join(f"{k} ({v})" for k, v in spec.args_schema.items()) or "none"
            lines.append(f"- {spec.name}: {spec.description} Args: {args}")
        return "\n".join(lines)


def build_default_catalog(
    search_code: SearchRelevantCodeUseCase,
    propose_fix: ProposeFixUseCase,
    generate_fix: GenerateFixUseCase | None = None,
) -> ToolCatalog:
    catalog = ToolCatalog()
    catalog.register(
        ToolSpec(
            name="read_issue",
            description="Read the GitHub issue being worked on (title, body, labels).",
            args_schema={},
            handler=lambda issue: Issue.from_dict(issue).to_dict(),
        )
    )
    catalog.register(
        ToolSpec(
            name="search_code",
            description="Search the repository for code relevant to the issue.",
            args_schema={"query": "regex or keywords to search for"},
            handler=lambda query, workspace=".": search_code.execute(
                query, workspace
            ).to_dict(),
        )
    )
    catalog.register(
        ToolSpec(
            name="propose_edit",
            description=(
                "Propose a code fix as a unified diff for a single file. "
                "The diff is stored for human review; it is never auto-applied."
            ),
            args_schema={
                "path": "file path to edit",
                "original": "current file content",
                "updated": "proposed new file content",
            },
            handler=lambda path, original, updated: propose_fix.execute(
                path, original, updated
            ).to_dict(),
        )
    )
    if generate_fix is not None:
        catalog.register(
            ToolSpec(
                name="draft_fix",
                description=(
                    "Have the LLM draft a fix for one file and return it as a "
                    "unified diff for human review; it is never auto-applied."
                ),
                args_schema={
                    "path": "file path to fix",
                    "original": "current file content",
                    "guidance": "optional extra instructions for the drafter",
                },
                handler=lambda path, original, guidance="", issue=None, analysis=None: (
                    generate_fix.execute(
                        issue or {}, analysis, path, original, guidance
                    ).to_dict()
                ),
            )
        )
    return catalog
