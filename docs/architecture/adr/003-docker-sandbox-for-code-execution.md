# ADR-003: Docker Sandboxing for Code Execution

**Status**: accepted (implementation lands with the test_verification context)

## Context

Agent-generated code is untrusted and must not affect the host system.

## Decision

Every test run happens in a fresh Docker container with no network access,
read-only root filesystem, and memory limits. Until that lands, nothing the
agent produces is executed at all — fixes exist only as unified diffs
pending human approval.

## Trade-offs

~3 second overhead per test run for container creation. Accepted because
security is non-negotiable for code execution.
