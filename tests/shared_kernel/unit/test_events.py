"""In-process domain event bus."""

from __future__ import annotations

from shared_kernel.events import (
    DomainEvent,
    EventBus,
    IssueAnalyzed,
    WorkflowFinished,
)


def test_publish_reaches_subscribed_handler():
    bus = EventBus()
    seen: list[DomainEvent] = []
    bus.subscribe(IssueAnalyzed, seen.append)

    event = IssueAnalyzed(workflow_id="wf-1", classification="bug")
    bus.publish(event)

    assert seen == [event]
    assert event.occurred_at  # timestamp auto-populated


def test_handlers_are_type_scoped():
    bus = EventBus()
    seen: list[DomainEvent] = []
    bus.subscribe(WorkflowFinished, seen.append)

    bus.publish(IssueAnalyzed(workflow_id="wf-1", classification="bug"))
    assert seen == []


def test_subscribing_to_base_type_receives_all_events():
    bus = EventBus()
    seen: list[DomainEvent] = []
    bus.subscribe(DomainEvent, seen.append)

    bus.publish(IssueAnalyzed(workflow_id="wf-1"))
    bus.publish(WorkflowFinished(workflow_id="wf-1", status="done"))
    assert len(seen) == 2


def test_handler_failure_does_not_break_publishing():
    bus = EventBus()
    seen: list[DomainEvent] = []

    def broken(_event):
        raise RuntimeError("boom")

    bus.subscribe(IssueAnalyzed, broken)
    bus.subscribe(IssueAnalyzed, seen.append)

    bus.publish(IssueAnalyzed(workflow_id="wf-1"))  # must not raise
    assert len(seen) == 1
