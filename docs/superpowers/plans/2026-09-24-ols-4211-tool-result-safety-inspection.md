# OLS-4211 Tool-Result Safety Inspection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the offline-testable DeepAgents tool-result inspection foundation: strict classifier contracts, complete-result chunking, bounded retries, deadline propagation, controlled telemetry, and default-enabled configuration.

**Architecture:** Keep inspection in a focused package with an injected async `ClassifierClient`; fake clients exercise all behavior without a cluster or real model. Provider adapters remain unchanged in OLS-4211, while OLS-4212 will later attach the inspector at the DeepAgents tool-result boundary. The package serializes effective results before token-aware splitting and never logs untrusted content.

**Tech Stack:** Python 3.12, Pydantic v2, LangChain message/model interfaces, asyncio, OpenTelemetry, pytest/pytest-asyncio.

**Spec:** `/home/vimalkum/src/ols/.ai/spec/what/tool-result-inspection.md`; sandbox specs `.ai/spec/what/configuration.md` and `.ai/spec/what/provider-contract.md`.

## Global Constraints

- Inspection defaults to enabled; only case-insensitive `true` and `false` are accepted when configured.
- Classifier requests contain only tool name, result type, chunk index/count, and untrusted content.
- Classifier responses are strict and contain only `injectionDetected` and `category`.
- Every effective result is inspected completely, sequentially, with 256-token adjacent overlap.
- Classifier failures retry three total times with 0.5s then 1.0s delays and fail closed.
- Malicious decisions are final and are never retried.
- No tool-result text, prompts, credentials, reasoning, or raw classifier output may enter telemetry or errors.
- Gemini ADK and OpenAI Agents remain unchanged.
- Rejected-result termination/interception belongs to OLS-4212, not this ticket.
- Reuse existing Pydantic, provider-client, and OpenTelemetry dependencies; add no classifier/rule-engine dependency.

## Review Focus

- A false decision with a non-`none` category is rejected; test in strict decision validation.
- A malicious decision with `unknown` is valid; test in strict decision validation.
- UTF-8 and structured values are serialized before chunking; test in chunking.
- A failure at any chunk prevents later chunks and preserves no content in errors; test in inspection orchestration.
- Deadline exhaustion prevents sleeping or starting another attempt; test with a controllable clock/sleeper.

### Task 1: Configuration parser

**Files:**
- Modify: `src/lightspeed_agentic/config.py`
- Test: `tests/test_config.py`

- [x] Add parser tests for missing, empty, valid case-insensitive values, and invalid values.
- [x] Run the focused tests and observe the expected missing-function failure.
- [x] Implement `parse_tool_output_inspection_enabled()` with default `True` and explicit Boolean validation.
- [x] Run `uv run pytest tests/test_config.py -k tool_output_inspection -q`.

### Task 2: Strict classifier contract

**Files:**
- Create: `src/lightspeed_agentic/inspection/models.py`
- Test: `tests/test_tool_result_inspection_models.py`

- [ ] Add tests for exact fields, extra-field rejection, strict Boolean rejection, allowed categories, and category invariants.
- [ ] Implement frozen request/decision models with Pydantic strict validation.
- [ ] Run the focused model tests.

### Task 3: Serialization and token chunking

**Files:**
- Create: `src/lightspeed_agentic/inspection/chunking.py`
- Test: `tests/test_tool_result_inspection_chunking.py`

- [ ] Add tests for strings, mappings, lists, errors, source order, no truncation, overlap, and boundary-crossing content.
- [ ] Implement serialization of effective values and an injected token codec with reserved instruction/output budget.
- [ ] Implement sequential chunks with 256-token overlap and no maximum chunk count.
- [ ] Run focused chunking tests.

### Task 4: Classifier protocol and inspection orchestration

**Files:**
- Create: `src/lightspeed_agentic/inspection/inspector.py`
- Create: `src/lightspeed_agentic/inspection/errors.py`
- Test: `tests/test_tool_result_inspection.py`

- [ ] Add fake-client tests for benign, malicious, refusal, malformed, timeout, provider error, disabled, first/middle/last malicious chunks, and request redaction.
- [ ] Implement `ClassifierClient` protocol and request execution with no tools/history/attachments/skills/main prompt in the contract.
- [ ] Implement sequential chunk inspection, final malicious decisions, and fail-closed classifier errors.
- [ ] Implement three attempts with exact delays and propagated remaining deadline.
- [ ] Run focused orchestration tests.

### Task 5: Controlled telemetry

**Files:**
- Modify: `src/lightspeed_agentic/inspection/inspector.py`
- Test: `tests/test_tool_result_inspection_telemetry.py`

- [ ] Add span tests for `tool_result.inspection`, controlled attributes, outcomes, and attempt/chunk counts.
- [ ] Add log/span assertions proving result content, prompts, raw responses, credentials, and classifier reasoning are absent.
- [ ] Implement controlled span/log reporting only.
- [ ] Run telemetry tests.

### Task 6: Production classifier adapter boundary

**Files:**
- Create: `src/lightspeed_agentic/inspection/client.py`
- Test: `tests/test_tool_result_inspection_client.py`

- [ ] Add fake model tests proving the classifier call contains only the contract messages and strict output schema.
- [ ] Implement the active-provider model adapter with no tools/history/RAG/attachments/skills/main-request prompt, disabled reasoning, temperature zero where supported, and bounded output.
- [ ] Keep provider-specific SDK imports lazy.
- [ ] Run client tests.

### Task 7: Package and regression verification

**Files:**
- Create/modify: `src/lightspeed_agentic/inspection/__init__.py`
- Test: existing suite

- [ ] Export only the intended inspection interfaces.
- [ ] Run `make lint`.
- [ ] Run `make test`.
- [ ] Review the diff for sensitive-content logging and accidental Gemini/OpenAI changes.
- [ ] Commit with an `OLS-4211`-prefixed message.
