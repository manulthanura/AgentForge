"""Application-level composition root.

Assembles every bounded context's adapters from Settings and hands back a
ready-to-use Application container. Entry points (main.py, the FastAPI app)
call this instead of wiring adapters themselves.

Adapter selection is configuration-only:
- LLM_PROVIDER picks the LLM adapter (anthropic | openai | ollama | openrouter).
- CODE_SEARCHER picks the code searcher (tree_sitter | filesystem).
- GITHUB_TOKEN + GITHUB_REPO enable the GitHub reader and PR client.
- SLACK_WEBHOOK_URL / SMTP_HOST+SMTP_TO enable notification channels.
- REQUIRE_APPROVAL gates finalization behind human sign-off (Phase 3).
"""

from __future__ import annotations

from dataclasses import dataclass

from approval.application.handle_response import HandleApprovalResponseUseCase
from approval.application.handle_timeout import HandleTimeoutUseCase
from approval.application.ports import ApprovalRepository
from approval.application.request_approval import RequestApprovalUseCase
from approval.infrastructure.in_memory_repo import InMemoryApprovalRepository
from approval.infrastructure.postgres_approval_repo import PostgresApprovalRepository
from code_intelligence.application.ports import CodeSearcher
from code_intelligence.infrastructure.fallback_searcher import FallbackCodeSearcher
from code_intelligence.infrastructure.filesystem_searcher import (
    FilesystemCodeSearcher,
)
from code_intelligence.infrastructure.tree_sitter_searcher import (
    TreeSitterCodeSearcher,
)
from fix_generation.application.generate_fix import GenerateFixUseCase
from fix_generation.infrastructure.llm_fix_drafter import LLMFixDrafter
from issue_intake.application.ports import IssueReader
from issue_intake.infrastructure.github_issue_reader import GitHubIssueReader
from notification.application.ports import Notifier
from notification.application.send_notification import SendNotificationUseCase
from notification.infrastructure.email_notifier import EmailNotifier
from notification.infrastructure.slack_notifier import SlackNotifier
from pull_request.application.create_pull_request import CreatePullRequestUseCase
from pull_request.infrastructure.github_pr_client import GitHubPRClient
from shared_kernel.config.settings import Settings, get_settings
from shared_kernel.events import EventBus
from shared_kernel.llm import LLMProvider, RetryingLLMProvider, get_provider
from shared_kernel.observability import init_tracing
from shared_kernel.resilience import RetryPolicy
from workflow_orchestration.application.ports import WorkflowEngine
from workflow_orchestration.application.resume_workflow import ResumeWorkflowUseCase
from workflow_orchestration.application.run_workflow import RunWorkflowUseCase
from workflow_orchestration.bootstrap import build_workflow_engine


@dataclass
class Application:
    settings: Settings
    provider: LLMProvider
    code_searcher: CodeSearcher
    generate_fix: GenerateFixUseCase
    engine: WorkflowEngine
    run_workflow: RunWorkflowUseCase
    resume_workflow: ResumeWorkflowUseCase
    approval_repository: ApprovalRepository
    request_approval: RequestApprovalUseCase
    handle_approval_response: HandleApprovalResponseUseCase
    handle_approval_timeout: HandleTimeoutUseCase
    send_notification: SendNotificationUseCase
    issue_reader: IssueReader | None = None
    create_pull_request: CreatePullRequestUseCase | None = None


def _build_code_searcher(settings: Settings) -> CodeSearcher:
    if settings.code_searcher == "filesystem":
        return FilesystemCodeSearcher()
    # Primary AST search degrades to the filesystem scan on failure (R-09).
    return FallbackCodeSearcher(
        primary=TreeSitterCodeSearcher(), fallback=FilesystemCodeSearcher()
    )


def _build_notifiers(settings: Settings) -> list[Notifier]:
    notifiers: list[Notifier] = []
    if settings.slack_webhook_url:
        notifiers.append(
            SlackNotifier(
                webhook_url=settings.slack_webhook_url,
                default_channel=settings.slack_approval_channel,
            )
        )
    if settings.smtp_host and settings.smtp_to:
        notifiers.append(
            EmailNotifier(
                host=settings.smtp_host,
                port=settings.smtp_port,
                sender=settings.smtp_from,
                recipient=settings.smtp_to,
            )
        )
    return notifiers


def build_application(
    settings: Settings | None = None,
    provider: LLMProvider | None = None,
    checkpointer=None,
    repository=None,
    event_bus: EventBus | None = None,
    approval_repository: ApprovalRepository | None = None,
    notifiers: list[Notifier] | None = None,
) -> Application:
    settings = settings or get_settings()
    init_tracing(settings)
    if provider is None:
        # Transient LLM failures (429/5xx/connection) back off and retry
        # (R-02); explicitly injected providers are used as-is for tests.
        provider = RetryingLLMProvider(
            get_provider(settings), policy=RetryPolicy(**settings.retry_policy_args())
        )

    code_searcher = _build_code_searcher(settings)
    generate_fix = GenerateFixUseCase(LLMFixDrafter(provider))

    issue_reader: IssueReader | None = None
    create_pull_request: CreatePullRequestUseCase | None = None
    if settings.github_token and settings.github_repo:
        issue_reader = GitHubIssueReader(
            repo_full_name=settings.github_repo, token=settings.github_token
        )
        create_pull_request = CreatePullRequestUseCase(
            GitHubPRClient(
                repo_full_name=settings.github_repo, token=settings.github_token
            )
        )

    send_notification = SendNotificationUseCase(
        notifiers if notifiers is not None else _build_notifiers(settings)
    )
    if approval_repository is None:
        approval_repository = (
            PostgresApprovalRepository(settings.database_url)
            if settings.database_url
            else InMemoryApprovalRepository()
        )
    request_approval = RequestApprovalUseCase(
        repository=approval_repository,
        send_notification=send_notification if send_notification.channels else None,
    )
    handle_approval_timeout = HandleTimeoutUseCase(
        repository=approval_repository,
        send_notification=send_notification if send_notification.channels else None,
        reminder_hours=settings.approval_reminder_hours,
        timeout_hours=settings.approval_timeout_hours,
    )

    engine = build_workflow_engine(
        provider,
        settings=settings,
        checkpointer=checkpointer,
        event_bus=event_bus,
        searcher=code_searcher,
        generate_fix=generate_fix,
        request_approval_hook=request_approval.execute,
    )
    run_workflow = RunWorkflowUseCase(engine, repository, event_bus)
    resume_workflow = ResumeWorkflowUseCase(engine, repository, event_bus)
    handle_approval_response = HandleApprovalResponseUseCase(
        resumer=resume_workflow, repository=approval_repository
    )

    return Application(
        settings=settings,
        provider=provider,
        code_searcher=code_searcher,
        generate_fix=generate_fix,
        engine=engine,
        run_workflow=run_workflow,
        resume_workflow=resume_workflow,
        approval_repository=approval_repository,
        request_approval=request_approval,
        handle_approval_response=handle_approval_response,
        handle_approval_timeout=handle_approval_timeout,
        send_notification=send_notification,
        issue_reader=issue_reader,
        create_pull_request=create_pull_request,
    )
