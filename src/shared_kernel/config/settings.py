"""Application settings loaded from environment variables (and .env).

The env file carries credentials and selection switches only; model names
live in model_config.json (see ModelConfigStore).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()
load_dotenv(".env.local", override=True)


@dataclass(frozen=True)
class Settings:
    """Runtime configuration. Everything comes from the environment so that
    switching providers or databases never requires a code change."""

    log_level: str = field(
        default_factory=lambda: os.environ.get("LOG_LEVEL", "info").upper()
    )

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
    openrouter_api_key: str | None = field(
        default_factory=lambda: os.environ.get("OPENROUTER_API_KEY")
    )
    openrouter_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
        )
    )
    # Optional attribution headers OpenRouter uses for its public rankings.
    openrouter_site_url: str | None = field(
        default_factory=lambda: os.environ.get("OPENROUTER_SITE_URL")
    )
    openrouter_app_name: str | None = field(
        default_factory=lambda: os.environ.get("OPENROUTER_APP_NAME")
    )
    ollama_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "OLLAMA_BASE_URL", "http://localhost:11434"
        )
    )

    # Azure OpenAI.
    azure_openai_api_key: str | None = field(
        default_factory=lambda: os.environ.get("AZURE_OPENAI_API_KEY")
    )
    azure_openai_endpoint: str | None = field(
        default_factory=lambda: os.environ.get("AZURE_OPENAI_ENDPOINT")
    )
    azure_openai_api_version: str = field(
        default_factory=lambda: os.environ.get(
            "AZURE_OPENAI_API_VERSION", "2024-10-21"
        )
    )
    # Deployment name in the Azure resource; falls back to the model name.
    azure_openai_deployment: str | None = field(
        default_factory=lambda: os.environ.get("AZURE_OPENAI_DEPLOYMENT")
    )

    # Google Gemini.
    google_api_key: str | None = field(
        default_factory=lambda: os.environ.get("GOOGLE_API_KEY")
    )

    # Hugging Face (serverless Inference Providers or a dedicated Endpoint).
    huggingface_api_token: str | None = field(
        default_factory=lambda: os.environ.get("HUGGINGFACEHUB_API_TOKEN")
        or os.environ.get("HUGGINGFACE_API_KEY")
    )
    huggingface_endpoint_url: str | None = field(
        default_factory=lambda: os.environ.get("HUGGINGFACE_ENDPOINT_URL")
    )
    huggingface_task: str = field(
        default_factory=lambda: os.environ.get("HUGGINGFACE_TASK", "text-generation")
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

    # Local filesystem path the code searcher scans for a triggered workflow
    # (this process does not clone GITHUB_REPO itself — point this at an
    # existing checkout). Defaults to the current working directory.
    workspace_path: str = field(
        default_factory=lambda: os.environ.get("WORKSPACE_PATH", ".")
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
