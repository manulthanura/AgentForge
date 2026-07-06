# Bounded context: issue_intake
Feature: GitHub Issue Analysis
  As an AI agent
  I want to analyze GitHub issues and understand the problem
  So that I can propose relevant code fixes

  Background:
    Given the agent is connected to the GitHub repository "user/project"
    And the agent has access to the repository's codebase
    And the LLM service is available and responsive

  @phase1 @implemented
  Scenario: Analyze a well-described bug report
    Given a GitHub issue #42 exists with title "Login fails when email contains '+' character"
    And the issue body contains reproduction steps and error logs
    When the agent receives the issue via webhook
    Then the agent should extract the following structured data:
      | Field         | Value                                 |
      | issue_type    | bug                                   |
      | affected_area | authentication                        |
      | symptoms      | login failure with special characters |
      | severity      | high                                  |
    And the agent should identify potentially relevant files
    And the agent state should be saved to the state store

  @phase1 @implemented
  Scenario: Handle a vague issue with insufficient information
    Given a GitHub issue #43 exists with title "It doesn't work"
    And the issue body contains only "please fix"
    When the agent receives the issue via webhook
    Then the agent should classify the issue as "insufficient_information"
    And the agent should post a comment asking for:
      | Question                     |
      | Steps to reproduce the issue |
      | Expected vs actual behavior  |
      | Environment details          |
    And the agent should set its state to "awaiting_clarification"
    And the agent should NOT proceed to code search

  @phase2
  Scenario: Analyze a feature request
    Given a GitHub issue #44 exists with title "Add dark mode support"
    And the issue is labeled "enhancement"
    When the agent receives the issue via webhook
    Then the agent should classify the issue as "feature_request"
    And the agent should identify related existing code patterns
    And the agent should generate an implementation plan outline
    And the plan should include estimated complexity level

  @phase2
  Scenario: Handle duplicate issue detection
    Given a GitHub issue #45 exists with title "Login broken with special characters"
    And a previously processed issue #42 covers the same problem
    When the agent receives issue #45 via webhook
    Then the agent should detect similarity score above 0.85 with issue #42
    And the agent should post a comment linking to issue #42
    And the agent should label issue #45 as "duplicate"
    And the agent should NOT proceed to code fix workflow
