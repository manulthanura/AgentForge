# Bounded context: code_intelligence
Feature: Intelligent Code Search
  As an AI agent
  I want to find relevant code sections related to an issue
  So that I can understand the context before making changes

  Background:
    Given the agent has analyzed issue #42 about login failures
    And the repository has been indexed for code search

  @phase1 @implemented
  Scenario: Find relevant code using search
    Given the issue mentions "authentication" and "email validation"
    When the agent performs a code search
    Then the agent should identify at least the following files:
      | File                    | Relevance |
      | src/auth/login.py       | primary   |
      | src/utils/validators.py | secondary |
      | tests/test_auth.py      | reference |
    And the agent should parse the AST of primary files
    And the agent should extract function signatures and dependencies

  @phase2
  Scenario: Handle large codebase with many matches
    Given the code search returns more than 20 relevant files
    When the agent processes the search results
    Then the agent should rank files by relevance score
    And the agent should select the top 5 most relevant files
    And the agent should build a dependency graph for selected files
    And the total context should not exceed the LLM context window limit

  @phase1 @implemented
  Scenario: Handle no relevant code found
    Given the issue mentions a module that does not exist in the codebase
    When the agent performs a code search
    Then the agent should report "no relevant code found"
    And the agent should expand search to include:
      | Strategy                         |
      | Search by error message keywords |
      | Search by file path patterns     |
      | Search test files for clues      |
    And if still no results, the agent should escalate to human review

  @phase2
  Scenario: Parse code dependencies correctly
    Given the agent found the relevant file "src/auth/login.py"
    When the agent parses the file using tree-sitter
    Then the agent should extract:
      | Element       | Count |
      | Function defs | >= 1  |
      | Import stmts  | >= 1  |
      | Class defs    | >= 0  |
    And the agent should map import chains to understand side effects
