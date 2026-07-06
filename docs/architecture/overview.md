# Architecture Overview

AgentForge follows **Domain-Driven Design + Clean Architecture** with
**bounded contexts as the top-level cut** — code is grouped by business
capability, not by technical layer. A top-level `domain/`–`application/`–
`infrastructure/` split is exactly the anti-pattern this layout avoids (see
[ADR-004](adr/004-bounded-contexts-as-top-level-cut.md)).

## The contexts

```
src/
├── issue_intake/            # receiving + classifying GitHub issues
├── code_intelligence/       # finding and understanding relevant code
├── fix_generation/          # drafting fixes as reviewable diffs
├── test_verification/       # generating + sandbox-running tests (domain only, WIP)
├── approval/                # human-in-the-loop gates
├── pull_request/            # opening PRs for approved fixes
├── notification/            # delivering messages (Slack, email)
├── workflow_orchestration/  # the aggregate-root context — coordinates the rest
├── shared_kernel/           # cross-cutting only: LLM port, events, config,
│                            # persistence, security, resilience, observability
├── interfaces/http/         # FastAPI assembly mounting each context's routers
└── bootstrap.py             # application composition root
```

Every context keeps the same internal shape:

| Layer | Contains | May import |
|-------|----------|-----------|
| `domain/` | entities, value objects, pure services — no I/O, no SDKs | nothing outside the context |
| `application/` | use cases + **ports** (ABCs) they depend on | own domain, `shared_kernel`, other contexts' *application* layer (orchestration only) |
| `infrastructure/` | adapters implementing the ports (PyGithub, tree-sitter, psycopg, LangGraph, SMTP, httpx) | anything |
| `interfaces/` | HTTP routers / entry points | application layer |

`workflow_orchestration` is the deliberate exception: as the aggregate-root
context it *coordinates other contexts' use cases* (its tool catalog wires
`search_code` to code_intelligence, `draft_fix` to fix_generation, and so
on). No other context reaches across.

## Runtime shape

```
GitHub webhook ──▶ interfaces/http ──▶ RunWorkflowUseCase
                                          │
                                          ▼
                        LangGraph state machine (infrastructure)
             analyze_issue → route ⇄ execute_tool → notify_approval
                                          │              │
                                          ▼              ▼
                          PostgreSQL checkpoints    await_approval (interrupt)
                                                         │
Slack Approve/Reject ──▶ HandleApprovalResponse ──▶ ResumeWorkflowUseCase
```

- **State**: LangGraph checkpoints in Postgres hold the full step-by-step
  workflow state (survives restarts and multi-hour pauses); a `workflows`
  index table gives the queryable status view.
- **LLM access**: every context talks to the `LLMProvider` port in
  `shared_kernel/llm` — never to a provider SDK directly
  ([ADR-005](adr/005-provider-agnostic-llm-port.md)).
- **Events**: an in-process bus (`shared_kernel/events`) publishes
  `IssueAnalyzed`, `ToolExecuted`, `WorkflowPaused`, `WorkflowFinished`,
  `WorkflowEscalated` — handlers can't break the workflow (errors are
  swallowed and logged).
- **Composition**: only `src/bootstrap.py` (app-level) and each context's
  `bootstrap.py` know about concrete adapters. Selection is
  configuration-only: `LLM_PROVIDER`, `CODE_SEARCHER`, presence of
  `GITHUB_TOKEN`, etc.

## Source of truth

- Behavior specs: [`features/*.feature`](../../features/) — Gherkin per
  context, tagged `@phaseN` and `@implemented`.
- Decisions: [ADR index](adr/).
- Project brief and testing lenses: [`CLAUDE.md`](../../CLAUDE.md).
