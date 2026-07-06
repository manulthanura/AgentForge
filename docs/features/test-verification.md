# Test Verification

> **Status: partial.** The domain model exists; test *generation* and the
> Docker sandbox *runner* are the main remaining implementation work.

Verifying a proposed fix by generating tests and running them in an
isolated sandbox (F-04) — designed, decided, and modeled, but not yet
executing.

## What exists today

`src/test_verification/domain/models.py`:

- `TestResult` — one test's name, pass/fail, and captured output;
- `TestSuite` — a named collection; `passed` is true only when the suite is
  non-empty **and** every result passed (an empty suite never counts as
  green).

Workflow state and the approval request already carry a test-results
summary, and the PR body renders one — so the integration points are in
place for when the runner lands.

## The design (per [ADR-003](../architecture/adr/003-docker-sandbox-for-code-execution.md))

Agent-generated code is untrusted. Every test run happens in a fresh
Docker container with:

- no network access,
- read-only root filesystem and `--no-new-privileges` (S-02),
- memory limit `SANDBOX_MEMORY_LIMIT` (512m) and timeout
  `SANDBOX_TIMEOUT_SECONDS` (120s) — both already in `.env.example`,
- container destroyed after execution, crash logs captured, up to 2 fresh
  retries on sandbox crash.

## Planned shape

Following the same pattern as every other context: a `TestRunner` port in
`application/`, a Docker adapter in `infrastructure/`, and a
`generate_tests` / `run_tests` pair in the workflow's tool catalog. Test
failure triage (fix vs. test vs. environment, retry up to 3, then escalate)
is specified in `features/test_verification.feature`.
