Feature: MCP server connectivity
  Verifies: OLS-3443 / OLS-3445 (MCP server connectivity for agentic sandbox)
  The sandbox parses LIGHTSPEED_MCP_SERVERS, resolves credentials, connects
  to configured MCP servers, and can invoke MCP-provided tools during a run.

  Background:
    Given the sandbox service is running with MCP servers configured

  Scenario: Batch run succeeds with MCP servers configured
    Given a simple non-skill query has been prepared
    When I run the agent with the prepared query and no output schema
    Then the run completes successfully
    And success is true
    And the response has a non-empty summary

  Scenario: Agent can invoke an MCP tool and use its output
    Given an MCP tool invocation query has been prepared
    When I run the agent with the prepared schema and query
    Then the run completes successfully
    And success is true
    And the response summary contains the sentinel namespace from the tool

  Scenario: Agent returns a graceful error envelope when a tool call fails
    Given an MCP query targeting a failing tool has been prepared
    When I run the agent with the prepared schema and query
    Then the batch job completes
    And success is false
    And the response has a non-empty summary
    And the response summary indicates an MCP tool failure
