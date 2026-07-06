# Architecture Decision Records

| ADR | Decision | Status |
|-----|----------|--------|
| [001](001-langgraph-over-crewai-autogen.md) | LangGraph over CrewAI / AutoGen | accepted |
| [002](002-postgresql-for-state-not-redis.md) | PostgreSQL for durable state, not Redis | accepted |
| [003](003-docker-sandbox-for-code-execution.md) | Docker sandboxing for code execution | accepted |
| [004](004-bounded-contexts-as-top-level-cut.md) | Bounded contexts as the top-level cut | accepted |
| [005](005-provider-agnostic-llm-port.md) | Provider-agnostic LLM port, env-selected adapters | accepted |
| [006](006-approval-gate-via-langgraph-interrupt.md) | Approval gate via `interrupt()` split across two nodes | accepted |
| [007](007-model-names-outside-env.md) | Model names in `model_config.json`, never in `.env` | accepted |

Format: short context → decision → trade-offs. New ADRs get the next
number; superseded ones are marked, never deleted.
