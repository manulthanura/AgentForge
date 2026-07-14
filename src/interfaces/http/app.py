"""HTTP assembly: one FastAPI app mounting each context's routers.

Routers stay inside their bounded contexts; this module only composes them
around a shared Application container:

- workflow_orchestration: GitHub webhook receiver + workflow status
- approval:               Slack interactions (Approve / Reject)
- shared_kernel:          admin model-config PATCH

Run locally with:  uvicorn --factory interfaces.http.app:create_app
"""

from __future__ import annotations

from fastapi import FastAPI

from approval.interfaces.slack import router as slack_router
from bootstrap import Application, build_application
from shared_kernel.config.model_config import ModelConfigStore
from shared_kernel.config.settings import Settings, get_settings
from shared_kernel.interfaces.admin import router as admin_router
from shared_kernel.observability import configure_logging
from workflow_orchestration.interfaces.webhook import router as webhook_router


def _default_checkpointer(settings: Settings):
    """Long-lived checkpointer: Postgres pool when configured, else memory."""
    if settings.database_url:
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg import Connection
        from psycopg.rows import dict_row

        conn = Connection.connect(
            settings.database_url, autocommit=True, row_factory=dict_row
        )
        checkpointer = PostgresSaver(conn)
        checkpointer.setup()
        return checkpointer

    from langgraph.checkpoint.memory import InMemorySaver

    return InMemorySaver()


def create_app(
    application: Application | None = None,
    settings: Settings | None = None,
    checkpointer=None,
    model_config_store: ModelConfigStore | None = None,
) -> FastAPI:
    settings = settings or (application.settings if application else get_settings())
    configure_logging(settings)
    if application is None:
        if checkpointer is None:
            checkpointer = _default_checkpointer(settings)
        application = build_application(settings=settings, checkpointer=checkpointer)

    app = FastAPI(title="AgentForge", version="0.3.0")
    app.state.settings = settings
    app.state.application = application
    app.state.model_config_store = model_config_store or ModelConfigStore()

    app.include_router(webhook_router)
    app.include_router(slack_router)
    app.include_router(admin_router)

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "provider": application.provider.name}

    return app
