"""Composition root for the orchestration context.

This is the one place allowed to know about every layer: it wires other
contexts' use cases, infrastructure adapters, and the LangGraph engine
together. The app-level composition root (src/bootstrap.py) calls this with
the adapters chosen by configuration.
"""

from __future__ import annotations

from code_intelligence.application.ports import CodeSearcher
from code_intelligence.application.search_relevant_code import (
    SearchRelevantCodeUseCase,
)
from code_intelligence.infrastructure.filesystem_searcher import (
    FilesystemCodeSearcher,
)
from fix_generation.application.generate_fix import GenerateFixUseCase
from fix_generation.application.propose_fix import ProposeFixUseCase
from issue_intake.application.analyze_issue import AnalyzeIssueUseCase
from shared_kernel.config.settings import Settings, get_settings
from shared_kernel.events import EventBus
from shared_kernel.llm import LLMProvider

from .application.routing import AgentRouter
from .application.run_workflow import RunWorkflowUseCase
from .application.tools import build_default_catalog
from .infrastructure.langgraph.engine import LangGraphWorkflowEngine
from .infrastructure.langgraph.graph import build_graph
from .infrastructure.langgraph.nodes import ApprovalHook


def build_agent_graph(
    provider: LLMProvider,
    settings: Settings | None = None,
    checkpointer=None,
    event_bus: EventBus | None = None,
    searcher: CodeSearcher | None = None,
    generate_fix: GenerateFixUseCase | None = None,
    request_approval_hook: ApprovalHook | None = None,
):
    """Wire the agent and compile its state machine.

    ``searcher`` defaults to the dependency-free filesystem adapter;
    ``generate_fix`` adds the LLM-backed draft_fix tool when provided;
    ``request_approval_hook`` is called with the reviewer payload when a
    workflow pauses at the approval gate.
    """
    settings = settings or get_settings()
    analyze_issue_uc = AnalyzeIssueUseCase(provider)
    catalog = build_default_catalog(
        search_code=SearchRelevantCodeUseCase(searcher or FilesystemCodeSearcher()),
        propose_fix=ProposeFixUseCase(),
        generate_fix=generate_fix,
    )
    router = AgentRouter(provider, catalog)
    return build_graph(
        analyze_issue_uc,
        router,
        catalog,
        settings=settings,
        checkpointer=checkpointer,
        event_bus=event_bus,
        request_approval_hook=request_approval_hook,
    )


def build_workflow_engine(
    provider: LLMProvider,
    settings: Settings | None = None,
    checkpointer=None,
    event_bus: EventBus | None = None,
    searcher: CodeSearcher | None = None,
    generate_fix: GenerateFixUseCase | None = None,
    request_approval_hook: ApprovalHook | None = None,
) -> LangGraphWorkflowEngine:
    """One engine per app: run and resume must share the compiled graph."""
    graph = build_agent_graph(
        provider,
        settings,
        checkpointer,
        event_bus,
        searcher,
        generate_fix,
        request_approval_hook,
    )
    return LangGraphWorkflowEngine(graph)


def build_run_workflow_use_case(
    provider: LLMProvider,
    settings: Settings | None = None,
    checkpointer=None,
    repository=None,
    event_bus: EventBus | None = None,
    searcher: CodeSearcher | None = None,
    generate_fix: GenerateFixUseCase | None = None,
) -> RunWorkflowUseCase:
    engine = build_workflow_engine(
        provider, settings, checkpointer, event_bus, searcher, generate_fix
    )
    return RunWorkflowUseCase(
        engine=engine,
        repository=repository,
        event_bus=event_bus,
    )
