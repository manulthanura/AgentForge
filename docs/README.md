# AgentForge Documentation

Start here: **[Getting Started](getting-started.md)** — from `git clone` to
a running stack and passing tests.

## Map

| | Doc | Answers |
|---|-----|---------|
| 🚀 | [getting-started.md](getting-started.md) | how do I run this from a fresh clone? |
| 🏗️ | [architecture/overview.md](architecture/overview.md) | how is the code organized (DDD bounded contexts)? |
| 🔁 | [architecture/workflow-lifecycle.md](architecture/workflow-lifecycle.md) | what is the agent state machine, how does pause/resume work? |
| 📜 | [architecture/adr/](architecture/adr/README.md) | why LangGraph, why Postgres, why Docker sandboxing, …? |
| 🌐 | [api/http-api.md](api/http-api.md) | endpoints, webhook signatures, admin API |
| 🧪 | [testing.md](testing.md) | test-suite layout and ground rules |
| 📦 | [deployment.md](deployment.md) | running it in production, monitoring, scaling |

## Features

| Doc | Capability | Status |
|-----|-----------|--------|
| [features/issue-intake.md](features/issue-intake.md) | classify issues, refuse vague ones | ✅ |
| [features/code-intelligence.md](features/code-intelligence.md) | AST-ranked code search with fallback | ✅ |
| [features/fix-generation.md](features/fix-generation.md) | LLM-drafted fixes as reviewable diffs | ✅ |
| [features/test-verification.md](features/test-verification.md) | generated tests in a Docker sandbox | 🚧 partial |
| [features/human-in-the-loop.md](features/human-in-the-loop.md) | approval gates, pause/resume, timeouts | ✅ |
| [features/pull-requests.md](features/pull-requests.md) | well-formed PRs after approval | ✅ (auto-wiring pending) |
| [features/llm-providers.md](features/llm-providers.md) | Anthropic / OpenAI / Ollama behind one port | ✅ |
| [features/reliability.md](features/reliability.md) | retries, degradation, corrupted checkpoints | ✅ |
| [features/observability.md](features/observability.md) | LangSmith traces + decision logs | ✅ |

## Other sources of truth

- Behavior specs (Gherkin): [`features/*.feature`](../features/) at the
  repo root — scenarios tagged `@implemented` have corresponding tests.
- Project brief and the six testing lenses: [`CLAUDE.md`](../CLAUDE.md).
