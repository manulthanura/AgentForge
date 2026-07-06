# ADR-002: PostgreSQL for State, Not Redis

**Status**: accepted

## Context

Agent state must survive process restarts and multi-hour pauses while a
human decides on an approval request.

## Decision

PostgreSQL for durable state — both the LangGraph checkpoint tables and our
own queryable index (`workflows`, `approvals`). Redis remains reserved for
the task queue and ephemeral cache in later phases.

## Trade-offs

Slightly higher latency for state operations (still < 10ms), but guarantees
ACID durability. Redis alone risks data loss on crash — unacceptable when
the lost state is a paused workflow a human already reviewed.
