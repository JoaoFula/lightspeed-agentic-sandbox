Feature: Reasoning configuration via LIGHTSPEED_REASONING_CONFIG
  Verifies: .ai/spec/what/configuration.md (rule 10a)
  Verifies: .ai/spec/what/provider-contract.md (rules 18–21)
  Harness: .ai/spec/what/e2e-testing.md
  Requires: LIGHTSPEED_REASONING_CONFIG on batch Jobs (see scripts/e2e-containers.sh).

  Scenario: Run succeeds with reasoning configured
    Given the sandbox service is running with reasoning configured
    And a simple non-skill query has been prepared
    When I run the agent with the prepared query and no output schema
    Then the run completes successfully
    And success is true
    And the response has a non-empty summary

  Scenario: Reasoning does not break structured output
    Given the sandbox service is running with reasoning configured
    And a flat output schema with required fields has been prepared
    When I run the agent with the prepared schema and query
    Then the run completes successfully
    And success is true
    And the response JSON validates against the output schema
