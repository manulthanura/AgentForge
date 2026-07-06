# ADR-001: LangGraph over CrewAI or AutoGen

**Status**: accepted

## Context

Multiple agent frameworks exist. We need state persistence,
human-in-the-loop, and fine-grained control over the agent loop.

## Decision

LangGraph — it models agents as explicit state machines with checkpointing
built in. Pausing at an approval gate is a first-class `interrupt()`;
resuming is `Command(resume=...)` against a checkpoint that survives
process restarts.

## Trade-offs

More boilerplate than CrewAI, but CrewAI's implicit orchestration makes
debugging harder. AutoGen's conversation-based model doesn't map well to
tool-use workflows. The explicit graph pays for itself the first time a
workflow has to resume from a 3-day-old checkpoint.
