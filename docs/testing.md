# Testing

The suite mirrors the bounded-context layout: **context leads, test type
nests inside it.**

```
tests/
├── conftest.py                  # shared fixtures; disables telemetry;
│                                # approval gate defaults OFF in tests
├── support/                     # FakeProvider/FailingProvider/FlakyProvider,
│                                # GitHub+Slack signing helpers
├── test_bootstrap.py            # composition root wiring
├── interfaces/                  # FastAPI assembly, signatures, admin API
└── <context>/
    ├── unit/                    # pure logic, everything faked
    ├── infrastructure/          # adapters against stubbed SDKs (no network)
    ├── integration/             # against the compose Postgres (auto-skip)
    └── e2e/                     # whole state machine / HTTP flows
```

## Running

```bash
uv run pytest                          # everything
uv run pytest tests/workflow_orchestration   # one context
uv run pytest tests/ -k reliability    # the reliability lens (R-01..R-09)
```

## Ground rules

- **No network, no real APIs.** LLMs are faked at the port
  (`tests/support/fakes.py`): `FakeProvider` pops scripted responses,
  `FailingProvider` always errors, `FlakyProvider` raises queued exceptions
  then recovers (outage simulation). PyGithub, httpx, and SMTP are stubbed
  at the adapter boundary. Retry tests inject `sleep`, so backoff asserts
  exact delays (`[2.0, 4.0, 8.0]`) without waiting.
- **Postgres-backed tests self-skip.** Anything needing the database probes
  it with a 2s timeout and skips with a clear reason when it's down — the
  suite passes with or without Docker. Bring it up for full coverage:
  `docker compose -f docker/docker-compose.yml up -d postgres migrate`.
- **Approval gates are opt-in per test.** `tests/conftest.py` sets
  `REQUIRE_APPROVAL=false`; Phase-3 pause/resume tests re-enable it via
  `monkeypatch`.
- **Features ↔ tests.** The Gherkin files in `features/` are the behavior
  spec; scenarios tagged `@implemented` have corresponding tests (e.g.
  `features/approval.feature` ↔
  `tests/workflow_orchestration/e2e/test_approval_pause_resume.py` and
  `test_http_approval_flow.py`).

## Writing new tests

- Put the test where the *capability* lives, not where the code file lives.
- Fake at ports, not at internals — if you need to reach into a private
  attribute of another context, the design (or the test) is wrong.
- Reliability-lens tests include "reliability" in the filename so
  `-k reliability` selects them.
