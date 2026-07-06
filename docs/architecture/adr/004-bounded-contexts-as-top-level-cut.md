# ADR-004: Bounded Contexts as the Top-Level Cut

**Status**: accepted

## Context

Two common ways to organize a DDD/Clean-Architecture codebase: technical
layers first (`src/domain/`, `src/application/`, `src/infrastructure/`) or
business capabilities first.

## Decision

Bounded contexts are the top-level directories under `src/`
(issue_intake, code_intelligence, fix_generation, approval, …), each
containing its own `domain/application/infrastructure/interfaces` layers.
Layers-first is the anti-pattern DDD practitioners complain about — it
groups code by *what kind of thing it is* instead of *what business
capability it belongs to*.

Consequences:

- A feature change touches one directory tree, not four.
- Context boundaries are import boundaries: only `workflow_orchestration`
  (the aggregate root) and the composition roots may reach across, and only
  via other contexts' application layers.
- Cross-cutting code that belongs to no capability lives in
  `shared_kernel/` — and *only* such code (LLM port, events, config,
  persistence, security, resilience, observability).
- Tests mirror the same cut: `tests/<context>/{unit,integration,e2e}`.

## Trade-offs

More directories and `__init__.py` ceremony than a flat layout; small
value-object-only contexts (e.g. `notification/domain`) look thin early on.
Accepted: the structure is the documentation.
