# Getting Started — from clone to running agent

This guide takes you from `git clone` to a running AgentForge stack
(PostgreSQL + migrations + HTTP API) and a passing test suite.

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.12+ | pinned in `.python-version` |
| [uv](https://docs.astral.sh/uv/) | 0.8+ | package/venv manager (`pip install uv` or the installer script) |
| Docker Desktop / Engine | any recent | Compose v2 (`docker compose`, not `docker-compose`) |

## 1. Clone and configure

```bash
git clone https://github.com/<you>/AgentForge.git
cd AgentForge
cp .env.example .env
```

The defaults in `.env.example` work out of the box for local development
(they match the compose Postgres credentials). Fill in what you need:

| Variable | Needed for | Default |
|----------|-----------|---------|
| `LLM_PROVIDER` | which LLM adapter runs (`anthropic` \| `openai` \| `ollama` \| `openrouter`) | `anthropic` |
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `OPENROUTER_API_KEY` | real LLM calls for the chosen provider | — |
| `OLLAMA_BASE_URL` | local models via Ollama (no key needed) | `http://localhost:11434` |
| `DATABASE_URL` | Postgres persistence + checkpoints | `postgresql://user:pass@localhost:5432/agentforge` |
| `GITHUB_TOKEN` + `GITHUB_REPO` | reading real issues / opening PRs | off when empty |
| `GITHUB_WEBHOOK_SECRET` / `SLACK_SIGNING_SECRET` | webhook signature checks (requests are rejected without them) | — |
| `REQUIRE_APPROVAL` | pause workflows for human sign-off before finalizing | `true` |

Model names deliberately do **not** live in `.env` — per-provider defaults are
in [`src/shared_kernel/config/model_config.json`](../src/shared_kernel/config/model_config.json)
and can be changed at runtime via the admin API (see
[docs/api/http-api.md](api/http-api.md)).

## 2. One-command stack (Docker)

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

This starts three services:

1. **postgres** — state store + LangGraph checkpoints (port 5432)
2. **migrate** — applies `migrations/*.sql` idempotently, then exits 0
3. **app** — the FastAPI service on <http://localhost:8000>
   (defaults to `LLM_PROVIDER=ollama` inside the container so it boots
   without API keys; export real credentials in your shell to override)

Check it:

```bash
curl http://localhost:8000/healthz
# {"ok":true,"provider":"ollama"}
```

Tear down with `docker compose -f docker/docker-compose.yml down`
(add `-v` to also wipe the database volume).

## 3. Local development (without the app container)

```bash
uv sync                      # create .venv and install all dependencies
uv run python main.py migrate   # apply migrations (needs Postgres up)
uv run python main.py demo      # run a sample issue through the agent
```

Run the API locally with hot reload:

```bash
uv run uvicorn --app-dir src --factory interfaces.http.app:create_app --reload
```

With `REQUIRE_APPROVAL=true` (the default) the demo workflow will pause at
the approval gate with status `awaiting_approval` — that is the
human-in-the-loop working as designed. See
[docs/features/human-in-the-loop.md](features/human-in-the-loop.md) for how
approval events resume it.

## 4. Run the tests

```bash
uv run pytest                     # full suite
uv run pytest tests/ -k reliability   # just the reliability lens (R-01..R-09)
```

Tests never call external APIs — LLM/GitHub/Slack are faked at their ports.
Postgres-backed integration and e2e tests run automatically when the compose
database is reachable and **skip cleanly when it is not**, so the suite
passes with or without Docker.

## 5. Where to go next

| Topic | Doc |
|-------|-----|
| Docs index | [README.md](README.md) |
| How the system is organized (DDD bounded contexts) | [architecture/overview.md](architecture/overview.md) |
| The agent state machine, pause/resume | [architecture/workflow-lifecycle.md](architecture/workflow-lifecycle.md) |
| Why key decisions were made | [architecture/adr/](architecture/adr/) |
| Issue classification + the vague-issue gate | [features/issue-intake.md](features/issue-intake.md) |
| Code search + ranking | [features/code-intelligence.md](features/code-intelligence.md) |
| Fixes as reviewable diffs | [features/fix-generation.md](features/fix-generation.md) |
| Sandboxed test verification (partial) | [features/test-verification.md](features/test-verification.md) |
| Human approval gates | [features/human-in-the-loop.md](features/human-in-the-loop.md) |
| PR creation after approval | [features/pull-requests.md](features/pull-requests.md) |
| Swapping LLM providers | [features/llm-providers.md](features/llm-providers.md) |
| Retries, fallbacks, corrupted checkpoints | [features/reliability.md](features/reliability.md) |
| Tracing + decision logs | [features/observability.md](features/observability.md) |
| HTTP endpoints + webhook signatures | [api/http-api.md](api/http-api.md) |
| Test suite layout | [testing.md](testing.md) |
| Production deployment + monitoring | [deployment.md](deployment.md) |

## Troubleshooting

- **`docker compose up` fails with "no configuration file"** — the compose
  file lives in `docker/`; pass `-f docker/docker-compose.yml` or run from
  that directory.
- **Webhook endpoints return 401** — signature verification fails closed:
  set `GITHUB_WEBHOOK_SECRET` / `SLACK_SIGNING_SECRET` and sign your requests
  (the test helpers in `tests/support/signing.py` show exactly how).
- **`LANGCHAIN_TRACING_V2 is set but LANGCHAIN_API_KEY is missing`** —
  harmless warning; tracing is hard-disabled until you add a LangSmith key.
- **Postgres tests skipped** — start the database:
  `docker compose -f docker/docker-compose.yml up -d postgres migrate`.
