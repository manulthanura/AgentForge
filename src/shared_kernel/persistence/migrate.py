"""Idempotent SQL migration runner.

Applies <repo-root>/migrations/*.sql in filename order, tracking applied
versions in schema_migrations. Also sets up LangGraph's Postgres checkpoint
tables (PostgresSaver.setup is itself idempotent).
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver

# src/shared_kernel/persistence/migrate.py -> repo root is three levels up
# from src/. Overridable for non-standard deployments.
MIGRATIONS_DIR = Path(
    os.environ.get("MIGRATIONS_DIR", Path(__file__).parents[3] / "migrations")
)


def run_migrations(database_url: str) -> list[str]:
    """Apply pending migrations; returns the list of newly applied versions."""
    applied_now: list[str] = []
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version    TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        already = {row[0] for row in rows}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in already:
                continue
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES (%s)",
                    (path.name,),
                )
            applied_now.append(path.name)

    # LangGraph checkpoint tables (checkpoints, checkpoint_writes, ...).
    with PostgresSaver.from_conn_string(database_url) as saver:
        saver.setup()

    return applied_now
