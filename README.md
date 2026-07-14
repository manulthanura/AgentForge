# AgentForge - GitHub

An autonomous AI agent that handles real multi-step developer workflows —
reading GitHub issues, searching relevant code, drafting fixes, and opening
pull requests — with **human approval gates before every irreversible
action**.

Most AI agent demos show the happy path. AgentForge is built around what
happens when things go wrong: the LLM is down, the checkpoint is corrupted,
GitHub rate-limits you mid-search, or nobody answers the approval request
for three days.

```
GitHub issue #42 opened
  └▶ analyze_issue   classified: bug / authentication / high
  └▶ route           "Need to find the auth code first."  → search_code
  └▶ execute_tool    3 files ranked; src/auth/login.py is primary
  └▶ route           "Root cause is the email regex."     → draft_fix
  └▶ execute_tool    unified diff produced (never auto-applied)
  └▶ notify_approval reviewer pinged on Slack with diff + risk summary
  └▶ await_approval  ⏸  checkpointed to Postgres — for hours or days

  … 3 hours later, a human clicks Approve …

  └▶ finalize        ▶ resumed from the exact checkpoint → done
```

## Why it's interesting

- **Durable pause/resume** — the agent stops at an approval gate, persists
  its full state as a LangGraph checkpoint in PostgreSQL, and resumes days
  later (across process restarts) exactly where it paused.
- **Failure is a first-class path** — typed LLM errors with exponential
  backoff, GitHub retries honoring `Retry-After`, AST search degrading to a
  filesystem scan, corrupted checkpoints falling back to the last valid
  one, and a compound-failure guard that escalates to a human instead of
  looping forever.
- **Every decision is explained** — the router logs each tool choice with
  its reasoning as structured JSON and into workflow state; optional
  LangSmith tracing captures the full story per workflow.
- **Security that fails closed** — webhook endpoints reject unsigned
  requests (GitHub HMAC, Slack v0 signatures with a replay window); a
  forged approval can never resume a workflow.
- **Clean architecture, DDD-style** — nine bounded contexts, each with
  `domain / application / infrastructure / interfaces` layers; swapping
  Claude for GPT or a local Ollama model is a one-variable change.

## Quickstart

```bash
git clone https://github.com/<you>/AgentForge.git
cd AgentForge
cp .env.example .env
docker compose -f docker/docker-compose.yml up -d --build
curl http://localhost:8000/healthz
```

That's Postgres + migrations + the API on
[localhost:8000](http://localhost:8000). For local development, the demo
run, and troubleshooting: **[docs/getting-started.md](docs/getting-started.md)**.

```bash
uv sync && uv run pytest        # test suite — no network, no API keys needed
uv run python main.py demo      # run a sample issue through the agent
```

## Architecture

```
GitHub webhook ──▶ FastAPI ──▶ RunWorkflowUseCase
                                   │
                                   ▼
                 LangGraph state machine (checkpointed in Postgres)
        analyze_issue → route ⇄ execute_tool → notify_approval
                                   │                │
             tools: read_issue,    ▼                ▼
             search_code,     decision log    await_approval (interrupt ⏸)
             draft_fix,                             │
             propose_edit     Slack Approve/Reject ─┘─▶ resume ─▶ finalize
```

| Layer | Choice | Why |
|-------|--------|-----|
| Agent framework | LangGraph | explicit state machine, checkpointing, `interrupt()` for human-in-the-loop ([ADR-001](docs/architecture/adr/001-langgraph-over-crewai-autogen.md)) |
| State | PostgreSQL | ACID durability for multi-day pauses ([ADR-002](docs/architecture/adr/002-postgresql-for-state-not-redis.md)) |
| LLM | Anthropic / OpenAI / Ollama / OpenRouter / Azure OpenAI / Gemini / Hugging Face | one port, adapter picked by `LLM_PROVIDER` ([ADR-005](docs/architecture/adr/005-provider-agnostic-llm-port.md)) |
| Code search | tree-sitter AST → filesystem fallback | ranked relevance with graceful degradation |
| Sandbox | Docker (isolated, no network) | untrusted generated code ([ADR-003](docs/architecture/adr/003-docker-sandbox-for-code-execution.md)) |

Full tour: [docs/architecture/overview.md](docs/architecture/overview.md) ·
[docs/architecture/workflow-lifecycle.md](docs/architecture/workflow-lifecycle.md) ·
[ADR index](docs/architecture/adr/README.md)

## Documentation

Everything lives in **[docs/](docs/README.md)** — getting started, the
HTTP API and webhook signing, per-feature deep dives (code intelligence,
human-in-the-loop, reliability, observability, …), testing ground rules,
and deployment.

## Project status

Phases 1–4 (core loop, tools, human-in-the-loop, error recovery &
observability) are implemented and tested; behavior specs live in
[`features/*.feature`](features/) with `@implemented` tags. The Docker
sandbox test-runner and automatic post-approval PR wiring are the main
remaining items — each doc has an honest "not yet implemented" section.

## License

[MIT](LICENSE)

Project by [@manulthanura](https://manulthanura.com)