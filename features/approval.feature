# Bounded context: approval (with notification)
Feature: Human Approval Gateway
  As a developer
  I want to review and approve agent actions before they execute
  So that irreversible changes are always human-verified

  Background:
    Given the agent has completed code fix and test generation
    And approval is required before PR creation

  @phase3 @implemented
  Scenario: Request approval via Slack
    Given the approval channel is configured as "#agent-approvals"
    When the agent requests approval for PR creation
    Then a Slack message should be sent containing:
      | Element                  |
      | Issue summary and link   |
      | Proposed changes (diff)  |
      | Test results summary     |
      | Risk assessment          |
      | Approve / Reject buttons |
    And the agent state should transition to "awaiting_approval"
    And the agent should persist its full state to PostgreSQL

  @phase3 @implemented
  Scenario: Resume after approval granted
    Given the agent has been paused for 3 hours awaiting approval
    And a human clicks "Approve" on the Slack message
    When the approval event is received
    Then the agent should resume from the exact checkpoint
    And the agent should verify its state is still valid
    And the agent should proceed to create the pull request
    And the agent should post a confirmation message

  @phase3 @implemented
  Scenario: Handle rejection with feedback
    Given a human clicks "Reject" with comment "Try a different approach"
    When the rejection event is received
    Then the agent should:
      | Step                                   |
      | Acknowledge the rejection              |
      | Parse the human feedback               |
      | Re-enter the code fix generation phase |
      | Use the feedback as additional context |
    And the retry count should be incremented
    And if retry count exceeds 3, the agent should stop and report

  @phase3
  Scenario: Handle approval timeout
    Given the agent has been awaiting approval for 48 hours
    When the timeout threshold is reached
    Then the agent should send a reminder notification
    And if no response after another 24 hours:
      | Action                              |
      | Post a comment on the GitHub issue  |
      | Set agent state to "timed_out"      |
      | Release any held resources          |
      | Log the timeout for metrics tracking |

  @phase3 @implemented
  Scenario: Concurrent approval requests
    Given the agent has 3 pending approval requests for different issues
    When a human approves issue #42 but not #43 or #44
    Then only the agent workflow for issue #42 should resume
    And workflows for #43 and #44 should remain paused
    And each workflow should maintain independent state
