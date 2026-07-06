"""Application settings loaded from environment variables (and .env).

The env file carries credentials and selection switches only; model names
live in model_config.json (see ModelConfigStore).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    """Runtime configuration. Everything comes from the environment so that
    switching providers or databases never requires a code change."""

    llm_provider: str = field(
        default_factory=lambda: os.environ.get("LLM_PROVIDER", "anthropic").lower()
    )
    # Optional model override; defaults come from model_config.json.
    llm_model: str | None = field(default_factory=lambda: os.environ.get("LLM_MODEL"))

    anthropic_api_key: str | None = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY")
    )
    openai_api_key: str | None = field(
        default_factory=lambda: os.environ.get("OPENAI_API_KEY")
    )
    ollama_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )
    )

    database_url: str | None = field(
        default_factory=lambda: os.environ.get("DATABASE_URL")
    )

    # GitHub integration (Phase 2): issue reading and PR creation.
    github_token: str | None = field(
        default_factory=lambda: os.environ.get("GITHUB_TOKEN")
    )
    github_repo: str | None = field(
        default_factory=lambda: os.environ.get("GITHUB_REPO")
    )

    # Code searcher adapter: "tree_sitter" (default) or "filesystem".
    code_searcher: str = field(
        default_factory=lambda: os.environ.get("CODE_SEARCHER", "tree_sitter").lower()
    )

    # Webhook signature secrets (S-06): reject unsigned/forged payloads.
    github_webhook_secret: str | None = field(
        default_factory=lambda: os.environ.get("GITHUB_WEBHOOK_SECRET")
    )
    slack_signing_secret: str | None = field(
        default_factory=lambda: os.environ.get("SLACK_SIGNING_SECRET")
    )

    # Notifications (Phase 3).
    slack_webhook_url: str | None = field(
        default_factory=lambda: os.environ.get("SLACK_WEBHOOK_URL")
    )
    slack_approval_channel: str = field(
        default_factory=lambda: os.environ.get(
            "SLACK_APPROVAL_CHANNEL", "#agent-approvals"
        )
    )
    smtp_host: str | None = field(default_factory=lambda: os.environ.get("SMTP_HOST"))
    smtp_port: int = field(
        default_factory=lambda: int(os.environ.get("SMTP_PORT", "587"))
    )
    smtp_from: str = field(
        default_factory=lambda: os.environ.get("SMTP_FROM", "agentforge@localhost")
    )
    smtp_to: str | None = field(default_factory=lambda: os.environ.get("SMTP_TO"))

    # Human-in-the-loop approval gate (Phase 3).
    require_approval: bool = field(
        default_factory=lambda: os.environ.get("REQUIRE_APPROVAL", "true").lower()
        in {"1", "true", "yes"}
    )
    max_approval_retries: int = field(
        default_factory=lambda: int(os.environ.get("MAX_APPROVAL_RETRIES", "3"))
    )
    approval_timeout_hours: int = field(
        default_factory=lambda: int(os.environ.get("APPROVAL_TIMEOUT_HOURS", "72"))
    )
    approval_reminder_hours: int = field(
        default_factory=lambda: int(os.environ.get("APPROVAL_REMINDER_HOURS", "48"))
    )

    # Shared secret for admin endpoints (model-config PATCH).
    secret_key: str | None = field(
        default_factory=lambda: os.environ.get("SECRET_KEY") or None
    )

    # Resilience (Phase 4): retry/backoff and compound-failure guard.
    retry_max_attempts: int = field(
        default_factory=lambda: int(os.environ.get("RETRY_MAX_ATTEMPTS", "3"))
    )
    retry_base_delay: float = field(
        default_factory=lambda: float(os.environ.get("RETRY_BASE_DELAY", "2"))
    )
    max_consecutive_failures: int = field(
        default_factory=lambda: int(
            os.environ.get("MAX_CONSECUTIVE_FAILURES", "3")
        )
    )

    # Observability (LangSmith).
    tracing_enabled: bool = field(
        default_factory=lambda: os.environ.get(
            "LANGCHAIN_TRACING_V2", os.environ.get("LANGSMITH_TRACING", "false")
        ).lower()
        in {"1", "true", "yes"}
    )
    langchain_api_key: str | None = field(
        default_factory=lambda: os.environ.get("LANGCHAIN_API_KEY")
        or os.environ.get("LANGSMITH_API_KEY")
    )
    langchain_project: str = field(
        default_factory=lambda: os.environ.get("LANGCHAIN_PROJECT", "agentforge")
    )

    def retry_policy_args(self) -> dict:
        return {
            "max_retries": self.retry_max_attempts,
            "base_delay": self.retry_base_delay,
        }

    # Hard cap on router->tool loop iterations per workflow.
    max_agent_steps: int = field(
        default_factory=lambda: int(os.environ.get("MAX_AGENT_STEPS", "8"))
    )


def get_settings() -> Settings:
    return Settings()
