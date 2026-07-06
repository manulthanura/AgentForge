# Bounded context: workflow_orchestration
Feature: Agent Error Recovery
  As an AI agent
  I want to recover gracefully from tool failures
  So that the workflow completes even when things go wrong

  @phase2
  Scenario: GitHub API rate limit hit
    Given the agent is performing code search via GitHub API
    When the API returns HTTP 429 (rate limited)
    Then the agent should:
      | Step                                 |
      | Extract the retry-after header value |
      | Save current state to checkpoint     |
      | Schedule a retry after the cooldown  |
      | Log the rate limit event             |
    And the agent should resume from the checkpoint after cooldown

  @phase4
  Scenario: LLM service temporarily unavailable
    Given the agent is generating a code fix
    When the LLM API returns HTTP 503
    Then the agent should retry with exponential backoff:
      | Attempt | Delay |
      | 1       | 2s    |
      | 2       | 4s    |
      | 3       | 8s    |
    And if all retries fail, the agent should:
      | Action                        |
      | Save full state to checkpoint |
      | Notify the operator via Slack |
      | Schedule retry in 30 minutes  |

  @phase1 @implemented
  Scenario: LLM outage during issue analysis escalates cleanly
    Given the agent is analyzing an issue
    When every LLM call fails
    Then the workflow should end in status "escalated"
    And the failure reason should be recorded in the decision log
    And the workflow state should remain readable from the checkpoint store

  @phase1 @implemented
  Scenario: Tool failure is recorded, not fatal
    Given the router selects a tool with invalid arguments
    When the tool execution raises an error
    Then the error should be captured in the tool results
    And the workflow should continue routing
    And the router may still finish the workflow

  @phase1 @implemented
  Scenario: Runaway agent loop is stopped by the step budget
    Given the router keeps selecting the same tool
    When the configured MAX_AGENT_STEPS budget is exhausted
    Then the workflow should escalate to human review
    And the decision log should record "step budget exhausted"

  @phase2
  Scenario: Docker sandbox crash during test execution
    Given the agent is running tests in a Docker sandbox
    When the sandbox container crashes unexpectedly
    Then the agent should:
      | Step                                  |
      | Capture crash logs from the container |
      | Destroy the crashed container         |
      | Spin up a fresh sandbox               |
      | Retry test execution (max 2 retries)  |
    And if retries exhausted, report the failure with logs

  @phase4
  Scenario: State store connection lost mid-workflow
    Given the agent is saving a checkpoint to PostgreSQL
    When the database connection drops
    Then the agent should:
      | Step                                |
      | Buffer the state in local memory    |
      | Attempt reconnection with backoff   |
      | Flush buffered state once reconnected |
    And no workflow progress should be lost
