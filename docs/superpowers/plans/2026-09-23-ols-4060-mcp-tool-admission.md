# OLS-4060 MCP Tool Admission and Filtering Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Discover MCP tools once, admit only policy-compliant tools, and expose the same admitted tool set and validated RBAC metadata to every provider without exposing filtered tools to the LLM.

**Architecture:** Extend MCP configuration values with raw-source authentication classification, then add a provider-neutral admission layer that validates tool annotations and `_meta["openshift.io/rbac"]`. The admission layer returns admitted servers grouped with canonical tool definitions and validated metadata; providers convert that plan into SDK-specific runtime tools and omit any server when the SDK cannot enforce the allowed-tool set before model exposure.

**Tech Stack:** Python dataclasses, MCP Streamable HTTP, `langchain-mcp-adapters`, Google ADK, OpenAI Agents, pytest, standard structured logging.

**Spec:** `.ai/spec/what/configuration.md` rules 20a–20c; `.ai/spec/what/provider-contract.md` rules 16 and 31–33; Jira OLS-4060 under OLS-4059.

## Global Constraints

- Admission happens once per one-shot invocation after `tools/list` and before tools are exposed to the LLM.
- Kubernetes classification is derived from raw header `source` values before header resolution and applies to the entire server.
- Secret-only servers bypass the Kubernetes RBAC filter.
- Kubernetes non-read-only tools require structurally valid `rules`, `deriveFromArgs`, or `deriveFromManifest` metadata.
- Missing, empty, malformed, `noRbac: true`, and `unbounded: true` metadata is rejected.
- The sandbox performs structural validation only; the analysis agent resolves admitted metadata against actual call arguments and reports `PolicyRule`s.
- There is no oc-IR fallback.
- Filtered tools must never be exposed to the LLM; empty servers are omitted without failing the workflow.
- Logs must not contain tokens, secret values, authorization headers, complete RBAC payloads, or tool arguments.
- Provider adapters must consume one shared admission result and must not independently reclassify or apply a different policy.

## Review Focus

- A Kubernetes server whose service-account token cannot be resolved must remain classified as Kubernetes and must not bypass admission; pin this in raw-classification tests.
- Two servers exposing the same tool name must remain distinguishable; pin this in admission-result tests.
- A read-only annotation with `destructiveHint=true` must be rejected; pin this in annotation tests.
- A provider SDK that cannot enforce an allowlist before model exposure must omit the server rather than pass it unfiltered; pin this in each provider integration test.
- RBAC metadata must reach the model-visible tool contract without leaking credentials or full payloads into logs; pin this in provider/logging tests.

---

### Task 1: Define the canonical admission data model

**Files:**
- Modify: `src/lightspeed_agentic/mcp.py`
- Modify: `src/lightspeed_agentic/types.py`
- Test: `tests/test_mcp.py`
- Test: `tests/test_types.py`

**Interfaces:**
- Produces `MCPAuthClass`, `AdmittedMCPTool`, and `AdmittedMCPServer`.
- `AdmittedMCPTool` contains `name`, `description`, `input_schema`, `read_only`, and `rbac_metadata`.
- `AdmittedMCPServer` contains the resolved connection fields, `auth_class`, and an immutable sequence of admitted tools.
- Admission returns a plain list containing only non-empty admitted servers.

- [ ] **Step 1: Add failing dataclass tests** for raw auth classification fields, canonical tool metadata, server grouping, and omission of empty servers.
- [ ] **Step 2: Run** `pytest tests/test_mcp.py tests/test_types.py -q` and verify the new imports/constructors fail.
- [ ] **Step 3: Implement** frozen dataclasses with tuples for result collections. Keep provider SDK objects out of the shared result.
- [ ] **Step 4: Run** `pytest tests/test_mcp.py tests/test_types.py -q` and verify the model tests pass.

### Task 2: Preserve raw server classification during configuration parsing

**Files:**
- Modify: `src/lightspeed_agentic/mcp.py`
- Test: `tests/test_mcp.py`

**Interfaces:**
- `parse_mcp_servers()` returns `ResolvedMCPServer` values carrying `auth_class`.
- Classification is computed from raw header dictionaries before `_resolve_header()` is called.

- [ ] **Step 1: Add failing tests** for ServiceAccountToken classification, Secret classification, mixed headers, and unresolved service-account tokens retaining Kubernetes classification.
- [ ] **Step 2: Run** the focused classification tests and verify failure.
- [ ] **Step 3: Add** `auth_class` to `ResolvedMCPServer` and calculate it from raw `source` values before resolving headers.
- [ ] **Step 4: Run** `pytest tests/test_mcp.py -q`.
- [ ] **Step 5: Run** the existing MCP parsing tests to ensure header-resolution behavior is unchanged.

### Task 3: Implement structural RBAC admission policy

**Files:**
- Create: `src/lightspeed_agentic/mcp_admission.py`
- Test: `tests/test_mcp_admission.py`

**Interfaces:**
- `admit_tool(*, server_auth_class, tool_name, description, input_schema, annotations, metadata) -> AdmittedMCPTool | AdmissionRejection`.
- `admit_server(*, server, discovered_tools) -> AdmittedMCPServer | None`.
- Supported metadata forms are `rules`, `deriveFromArgs`, and `deriveFromManifest`.
- Rejection values use fixed safe reason identifiers such as `not_read_only`, `missing_rbac_metadata`, `empty_rbac_metadata`, `malformed_rbac_metadata`, `no_rbac`, and `unbounded`.

- [ ] **Step 1: Add failing tests** for non-Kubernetes admission, read-only admission, contradictory destructive annotations, each supported metadata form, missing/empty/malformed metadata, `noRbac`, and `unbounded`.
- [ ] **Step 2: Add failing tests** proving nested/unsupported metadata forms are rejected without attempting RBAC resolution.
- [ ] **Step 3: Run** `pytest tests/test_mcp_admission.py -q` and verify failure.
- [ ] **Step 4: Implement** top-level structural validation only. Do not resolve arguments or produce `PolicyRule`s.
- [ ] **Step 5: Run** the focused admission tests and verify they pass.
- [ ] **Step 6: Add** mixed-tool and all-tools-rejected server tests; verify an empty server returns `None`.

### Task 4: Add one-shot MCP discovery and admission orchestration

**Files:**
- Modify: `src/lightspeed_agentic/mcp_admission.py`
- Modify: `src/lightspeed_agentic/batch.py`
- Modify: `src/lightspeed_agentic/run_agent.py`
- Modify: `src/lightspeed_agentic/types.py`
- Test: `tests/test_mcp_admission.py`
- Test: `tests/test_batch.py`
- Test: `tests/test_run_agent.py`

**Interfaces:**
- Add `async discover_and_admit_mcp_servers(servers, *, correlation) -> list[AdmittedMCPServer]`.
- Discovery calls each server's `tools/list` once using resolved connection details.
- The function produces canonical tool definitions and applies the shared policy before provider creation/query.
- `ProviderQueryOptions.mcp_servers` changes to the admitted result type while preserving an empty default.

- [ ] **Step 1: Add mocked discovery tests** proving each server is queried once and that the result contains only admitted tools.
- [ ] **Step 2: Add tests** proving one server with no admitted tools is removed while other servers continue.
- [ ] **Step 3: Add a batch test** proving admission is performed before `run_agent_query()` and provider construction receives the admitted result.
- [ ] **Step 4: Run** focused tests and verify failure.
- [ ] **Step 5: Implement** the orchestration with provider-neutral discovery objects and no provider SDK tool objects in the result.
- [ ] **Step 6: Run** `pytest tests/test_mcp_admission.py tests/test_batch.py tests/test_run_agent.py -q`.

### Task 5: Define the model-visible RBAC contract

**Files:**
- Create: `src/lightspeed_agentic/mcp_prompt.py`
- Modify: `.ai/spec/what/provider-contract.md`
- Test: `tests/test_mcp_admission.py`

**Interfaces:**
- Add `model_visible_tool_description(tool: AdmittedMCPTool) -> str` or an equivalent provider-neutral rendering helper.
- The rendering includes the validated RBAC contract for mutating tools and explicit instructions that actual call arguments must be used to derive `PolicyRule`s.
- Rendering never includes resolved headers, tokens, or unrelated server configuration.

- [ ] **Step 1: Add tests** for read-only tools, static `rules`, `deriveFromArgs`, and `deriveFromManifest` rendering.
- [ ] **Step 2: Add tests** asserting secret/header values and complete connection configuration are absent.
- [ ] **Step 3: Run** focused tests and verify failure.
- [ ] **Step 4: Implement** deterministic, bounded rendering of the validated metadata into the model-visible tool description/contract.
- [ ] **Step 5: Update** the provider contract to state that metadata is model-visible through the tool definition, while the sandbox still performs structural validation only.
- [ ] **Step 6: Run** `pytest tests/test_mcp_admission.py -q`.

### Task 6: Enforce admitted tools in the DeepAgents provider

**Files:**
- Modify: `src/lightspeed_agentic/providers/deepagents.py`
- Test: `tests/test_deepagents.py`

**Interfaces:**
- DeepAgents loads MCP runtime tool objects through `MultiServerMCPClient`.
- It filters returned objects by the admitted tool names for the owning server and passes only those objects to `create_deep_agent(tools=...)`.
- It applies the model-visible RBAC contract to each admitted tool description where the SDK object permits it.

- [ ] **Step 1: Add failing tests** with admitted and rejected names, asserting only admitted objects reach `create_deep_agent()`.
- [ ] **Step 2: Add a test** asserting no MCP tools are passed when a server has no admitted tools.
- [ ] **Step 3: Run** focused DeepAgents tests and verify failure.
- [ ] **Step 4: Implement** name-based filtering after SDK loading and before agent construction.
- [ ] **Step 5: Run** `pytest tests/test_deepagents.py -q`.

### Task 7: Verify and enforce Gemini/OpenAI provider filtering

**Files:**
- Modify: `src/lightspeed_agentic/providers/gemini.py`
- Modify: `src/lightspeed_agentic/providers/openai.py`
- Modify: `src/lightspeed_agentic/mcp.py`
- Test: `tests/test_mcp.py`
- Test: `tests/test_gemini.py` or the existing Gemini provider test module
- Test: `tests/test_openai_schema.py` or the existing OpenAI provider test module

**Interfaces:**
- Each provider receives admitted server/tool data only.
- Each provider must apply a native pre-exposure tool filter when the installed SDK supports it.
- When that mechanism is unavailable or cannot be proven to filter before model exposure, the provider omits that server and logs a safe omission reason.

- [ ] **Step 1: Inspect the installed Google ADK and OpenAI Agents APIs** and write focused compatibility tests against the actual filtering hooks.
- [ ] **Step 2: Add failing provider tests** for admitted-name filtering and unsupported-filter omission.
- [ ] **Step 3: Run** the provider tests and verify failure.
- [ ] **Step 4: Implement** the native filters or explicit server omission; do not pass an unfiltered server as a fallback.
- [ ] **Step 5: Run** the Gemini/OpenAI focused tests.
- [ ] **Step 6: Update** `tests/test_mcp.py` conversion tests for the new admitted-server shape.

### Task 8: Add safe structured admission/removal logging

**Files:**
- Modify: `src/lightspeed_agentic/mcp_admission.py`
- Modify: `src/lightspeed_agentic/logging.py` only if the existing logger needs a structured event helper
- Test: `tests/test_mcp_admission.py`
- Test: `tests/test_logging.py` or the existing logging test module

**Interfaces:**
- Emit one structured event per filtered tool and one per removed server.
- Events contain server name, tool name where applicable, classification, reason, and available run/step correlation.
- Events exclude headers, token values, secrets, complete metadata payloads, and tool arguments.

- [ ] **Step 1: Add failing capture-log tests** for filtered tools and removed servers.
- [ ] **Step 2: Add assertions** that sensitive fixture values do not occur in captured records.
- [ ] **Step 3: Run** focused logging tests and verify failure.
- [ ] **Step 4: Implement** structured logging with fixed reason values and explicit safe fields.
- [ ] **Step 5: Run** the logging tests and the admission tests.

### Task 9: Full regression verification and spec cleanup

**Files:**
- Modify: `.ai/spec/what/configuration.md` only if implementation details require wording correction
- Modify: `.ai/spec/what/provider-contract.md` only if the final SDK behavior needs precise documentation
- Test: all affected MCP/provider test files

- [ ] **Step 1: Run** `pytest tests/test_mcp.py tests/test_mcp_admission.py tests/test_deepagents.py tests/test_run_agent.py tests/test_batch.py -q`.
- [ ] **Step 2: Run** `make test`.
- [ ] **Step 3: Run** `make lint`.
- [ ] **Step 4: Run** LSP diagnostics on all changed Python files and resolve errors introduced by the implementation.
- [ ] **Step 5: Verify** no provider path can receive an unfiltered MCP server and no admission log contains sensitive values.
- [ ] **Step 6: Update** the MCP e2e fixture only if the existing mock server can exercise admitted and rejected tools without requiring live credentials.
