"""AgentForge CLI entrypoint (composition root).

Commands:
    python main.py migrate           Apply database migrations.
    python main.py demo              Run a sample issue through the agent
                                     (requires LLM credentials for the
                                     provider selected by LLM_PROVIDER).
"""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from shared_kernel.config.settings import get_settings  # noqa: E402
from shared_kernel.llm import get_provider  # noqa: E402
from shared_kernel.persistence.migrate import run_migrations  # noqa: E402

SAMPLE_ISSUE = {
    "number": 42,
    "title": "Login fails when email contains '+' character",
    "body": (
        "Steps to reproduce:\n"
        "1. Register with alice+test@example.com\n"
        "2. Try to log in\n"
        "3. Login fails with 'invalid email' even though registration worked.\n\n"
        "Expected: login succeeds for any RFC-valid email."
    ),
    "labels": ["bug"],
}


def cmd_migrate() -> None:
    settings = get_settings()
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set; cannot run migrations.")
    applied = run_migrations(settings.database_url)
    print(
        f"Applied migrations: {', '.join(applied)}"
        if applied
        else "No pending migrations; schema is up to date."
    )


def cmd_demo() -> None:
    from bootstrap import build_application
    from workflow_orchestration.infrastructure.postgres_workflow_repo import (
        PostgresWorkflowRepository,
    )

    settings = get_settings()
    provider = get_provider(settings)
    print(f"Provider: {provider.name} (model: {provider.model})")
    print(f"Code searcher: {settings.code_searcher}")

    workflow_id = f"demo-{uuid.uuid4().hex[:8]}"
    repository = (
        PostgresWorkflowRepository(settings.database_url)
        if settings.database_url
        else None
    )

    def _run(checkpointer=None):
        app = build_application(
            settings=settings,
            provider=provider,
            checkpointer=checkpointer,
            repository=repository,
        )
        return app.run_workflow.execute(
            workflow_id, SAMPLE_ISSUE, workspace=settings.workspace_path
        )

    if settings.database_url:
        from langgraph.checkpoint.postgres import PostgresSaver

        with PostgresSaver.from_conn_string(settings.database_url) as checkpointer:
            final = _run(checkpointer)
    else:
        final = _run()

    print(f"\nWorkflow {workflow_id} finished with status: {final.get('status')}")
    print("\nDecision log:")
    for d in final.get("decisions", []):
        print(f"  [{d.get('node')}] {d.get('action')} — {d.get('reasoning', '')[:120]}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="agentforge")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="apply database migrations")
    sub.add_parser("demo", help="run a sample issue through the agent")
    args = parser.parse_args()
    if args.command == "migrate":
        cmd_migrate()
    elif args.command == "demo":
        cmd_demo()


if __name__ == "__main__":
    main()
