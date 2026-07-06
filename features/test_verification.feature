# Bounded context: test_verification
Feature: Test Generation for Code Fixes
  As an AI agent
  I want to generate tests that verify my code fix
  So that the fix can be validated automatically

  @phase2
  Scenario: Generate unit tests for a bug fix
    Given the agent has generated a fix for the email sanitization bug
    When the agent generates tests
    Then the tests should include:
      | Test Case                                       | Type     |
      | Test login with standard email                  | positive |
      | Test login with email containing '+'            | positive |
      | Test login with email containing special chars  | positive |
      | Test login with empty email                     | negative |
      | Test login with SQL injection attempt           | negative |
    And each test should follow the repository's testing conventions
    And tests should be placed in the correct test directory

  @phase2
  Scenario: Run generated tests in sandbox
    Given the agent has generated 5 test cases
    When the agent executes tests in the Docker sandbox
    Then all 5 tests should pass
    And test execution should complete within 60 seconds
    And the sandbox should be destroyed after execution
    And test results should be stored in the state store

  @phase2
  Scenario: Handle test failure
    Given the agent has generated tests and one test fails
    When the agent reviews the test failure output
    Then the agent should determine if the failure is in:
      | Source      | Action                     |
      | the fix     | revise the code fix        |
      | the test    | revise the test            |
      | environment | retry with different setup |
    And the agent should retry up to 3 times
    And if still failing, escalate to human review
