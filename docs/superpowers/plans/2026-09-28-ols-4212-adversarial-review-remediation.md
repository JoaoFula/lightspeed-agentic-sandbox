# OLS-4212 Adversarial Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close OLS-4212's adversarial-review gaps, including DeepAgents `task` subagent results, while preserving fail-closed safety and the approved audit path for passing content.

**Architecture:** Enforce inspection at the model-call boundary, after DeepAgents has applied filesystem offload, for both the main agent and an explicit general-purpose subagent. Keep classifier and telemetry payload-free; publish complete tool-result audit events only after the effective result passes inspection. Separate the stable safety marker from optional DeepAgents imports.

**Tech Stack:** Python 3.12, asyncio, pytest, Pydantic, LangChain/LangGraph, DeepAgents, OpenTelemetry, uv.

**Spec:** `../specs/2026-09-28-ols-4212-adversarial-review-design.md`; normative policy: `../../../.ai/spec/what/provider-contract.md`, `../../../.ai/spec/what/audit-logging.md`, and workspace `../../../../../../.ai/spec/what/tool-result-inspection.md`.

## Global Constraints

- Inspect the complete effective result before model use; do not truncate it to reduce classifier work.
- Inspection, setup, and classifier failures fail closed with `ToolResultSafetyInspectionFailed`.
- Rejected results MUST NOT enter model context, Result CRs, termination logs, developer logs, audit events, or inspection telemetry.
- Passing complete results MAY enter the approved AuditLogger content path; EventLogger and inspection telemetry remain payload-free.
- The classifier receives no tools, conversation history, RAG content, attachments, skills, or main-request system prompt, and uses no reasoning/thinking options.
- Gemini ADK and OpenAI Agents behavior remains unchanged; their import paths must not require DeepAgents/LangChain extras.
- Do not add dependencies or Prometheus metrics. Run tests offline.
- Keep OLS-4212 as one squashed commit before pushing; cluster validation requires a rebuilt image and is not authorized by this plan.

## Review Focus

- A ToolMessage nested in a Command or subagent report must be checked before its receiving model call; test both boundaries in Task 4.
- Filesystem offload can replace a large ToolMessage with a preview/reference; test the exact effective request seen by the model in Task 3.
- A response with a refusal plus text, unknown fields, or contradictory verdict fields must not be treated as benign; test in Task 1.
- UTF-8 multibyte sequences at chunk edges must remain valid and fully represented; test in Task 2. Keep the exact 256-byte overlap for ASCII; when UTF-8 boundary alignment requires it, preserve at least 256 bytes rather than emit invalid UTF-8.
- Cancellation at the Agent deadline and base-provider imports must preserve safety/error behavior without optional SDK imports; test in Task 5.

---

### Task 1: Enforce the strict classifier response contract

**Files:**
- Modify: `src/lightspeed_agentic/inspection/client.py`
- Modify: `src/lightspeed_agentic/inspection/errors.py` only if a new controlled response-issue value is required
- Test: `tests/test_tool_result_inspection_client.py`

**Interfaces:**
- Consumes: `ClassifierDecision` strict Pydantic model from `inspection/models.py`.
- Produces: `LangChainClassifierClient.classify(request, deadline=...)` accepts only the canonical two-field decision object; invalid envelopes raise payload-free `ClassifierResponseError` and become `InspectionError` in the existing inspection layer.

- [x] **Step 1: Add failing tests** for `{"injectionDetected":false,"category":"none","attack_detected":true}`, safe/unsafe legacy objects with contradictory fields, text plus a refusal content block, refusal-only blocks, and the two canonical valid decisions. Assert failures have controlled issue values and never include response text.
- [x] **Step 2: Run** `uv run pytest tests/test_tool_result_inspection_client.py -q`. Confirm the contradiction and mixed-refusal cases currently pass incorrectly.
- [x] **Step 3: Implement** strict top-level field validation and refusal detection before extracting text. Remove or narrow legacy normalization so no extra or conflicting field can become a canonical benign response; preserve only provider envelope handling that does not weaken the canonical schema.
- [x] **Step 4: Run** `uv run pytest tests/test_tool_result_inspection_client.py -q`; all strict-response tests pass.
- [x] **Step 5: Commit** the isolated classifier fix with an `OLS-4212` commit subject.

### Task 2: Make UTF-8 fallback chunk boundaries safe

**Files:**
- Modify: `src/lightspeed_agentic/inspection/chunking.py`
- Test: `tests/test_tool_result_inspection_chunking.py`

**Interfaces:**
- Consumes: the existing `TokenCodec` protocol and `chunk_tool_result(...)` API.
- Produces: chunks that decode independently as valid UTF-8 while respecting the configured capacity, retaining 256-token overlap (or at least 256 bytes when UTF-8 boundary alignment requires up to three extra bytes), and covering all serialized input.

- [x] **Step 1: Add failing tests** with `é`, `€`, and a four-byte character placed at both chunk end and overlap boundaries. Assert every chunk decodes, first/last chunks include the full input edges, ASCII chunks overlap by exactly 256 bytes, UTF-8-aligned chunks overlap by at least 256 bytes, and capacity constraints hold.
- [x] **Step 2: Run** `uv run pytest tests/test_tool_result_inspection_chunking.py -q`; confirm byte-boundary decoding fails.
- [x] **Step 3: Implement** UTF-8 boundary alignment in the fallback codec/chunker without dropping bytes, changing generic tokenizer behavior, or truncating input.
- [x] **Step 4: Run** `uv run pytest tests/test_tool_result_inspection_chunking.py -q`; all existing and new chunk tests pass.
- [x] **Step 5: Commit** the chunking fix with an `OLS-4212` commit subject.

### Task 3: Inspect effective model input after offload

**Files:**
- Modify: `src/lightspeed_agentic/inspection/middleware.py`
- Test: `tests/test_tool_result_inspection_middleware.py`

**Interfaces:**
- Consumes: the existing inspector callback `(tool_name: str, result_type: str, value: Any) -> Awaitable[Any]`.
- Produces: `ToolResultInspectionMiddleware.awrap_model_call(request, handler)` checks each newly model-visible ToolMessage before invoking `handler`; any inspection error or non-passing outcome raises the fixed `ToolResultSafetyInspectionFailed` marker. `is_passed(tool_name: str, result_type: str, tool_call_id: str, content: Any) -> bool` reports whether that exact classifier input signature passed, for event gating.

- [x] **Step 1: Add failing tests** for a new ToolMessage in `request.messages`, error-status ToolMessage, repeated previously inspected message, same ID with changed content, no-ID message, inspection failure, and cancellation during inspection. Assert the downstream model handler is not called on failure.
- [x] **Step 2: Add a middleware-order regression test** using DeepAgents `FilesystemMiddleware` with a large tool result. Verify inspection receives the offload preview/reference that the downstream model request sees, not the raw result alone.
- [x] **Step 3: Run** `uv run pytest tests/test_tool_result_inspection_middleware.py -q`; confirm model input is currently unguarded and offload changes the inspected boundary.
- [x] **Step 4: Implement** the model-call guard and per-middleware deduplication keyed by tool-call ID plus a digest of effective content, so changed content is re-inspected. Record successful signatures and expose `is_passed(tool_name, result_type, tool_call_id, content) -> bool` for provider event gating. Catch cancellation only around the inspector call and translate it to the safety marker; do not expose the message or exception.
- [x] **Step 5: Run** `uv run pytest tests/test_tool_result_inspection_middleware.py -q`; direct, offloaded, duplicate, and cancellation tests pass.
- [x] **Step 6: Commit** the model-boundary fix with an `OLS-4212` commit subject.

### Task 4: Guard the main agent and `task` subagent; gate result events

**Files:**
- Modify: `src/lightspeed_agentic/providers/deepagents.py`
- Modify: `src/lightspeed_agentic/run_agent.py` to separate developer and audit event copies
- Test: `tests/test_deepagents.py`
- Test: `tests/test_run_agent.py`
- Test: `tests/test_tool_result_inspection_middleware.py`

**Interfaces:**
- Consumes: Task 3's `ToolResultInspectionMiddleware.awrap_model_call` and `is_passed(tool_name, result_type, tool_call_id, content)` APIs, plus the provider's existing `inspect_tool_result_callback`.
- Produces: both main and general-purpose subagent model calls use the same callback; complete `ToolResultEvent` reaches AuditLogger only after inspection passes; DeepAgents EventLogger receives payload-free tool metadata.

- [x] **Step 1: Add failing integration tests** that create a DeepAgents graph with the main agent and explicit general-purpose `task` subagent. Verify a malicious subagent tool result prevents the subagent's next model call, and a malicious ToolMessage inside the parent `task` Command prevents the parent model call.
- [x] **Step 2: Add failing provider/event tests** verifying rejected tool output produces no ToolResultEvent, accepted output reaches AuditLogger complete, and EventLogger records contain neither tool arguments nor output. Preserve Gemini/OpenAI event logging behavior.
- [x] **Step 3: Run** the focused tests in `tests/test_deepagents.py` and `tests/test_run_agent.py`; confirm the subagent and event-leak tests fail before implementation.
- [x] **Step 4: Implement** an explicit general-purpose subagent configuration with inspection middleware while retaining its default name, purpose, model, and tools. Apply the same shared inspection middleware instance to the main agent and `task` subagent so both model boundaries use the same pass-signature registry. When inspection is enabled, buffer ToolMessage events; on the next AI stream item, release only messages for which the main middleware's `is_passed(tool_name, result_type, tool_call_id, content)` returns true. If inspection fails, discard the buffer and propagate the safety marker. In disabled mode, preserve normal event delivery. Send complete, non-truncated released events to AuditLogger and payload-free copies to EventLogger.
- [x] **Step 5: Run** `uv run pytest tests/test_deepagents.py tests/test_run_agent.py tests/test_tool_result_inspection_middleware.py -q`; all main-agent, subagent, event-ordering, and provider-isolation assertions pass.
- [x] **Step 6: Commit** the DeepAgents/task integration with an `OLS-4212` commit subject.

### Task 5: Preserve the safety failure across deadlines and optional imports

**Files:**
- Modify: `src/lightspeed_agentic/inspection/errors.py`
- Modify: `src/lightspeed_agentic/inspection/middleware.py`
- Modify: `src/lightspeed_agentic/run_agent.py`
- Modify: `src/lightspeed_agentic/batch.py`
- Test: `tests/test_run_agent.py`
- Test: `tests/test_batch.py`
- Test: `tests/test_optional_provider_imports.py`

**Interfaces:**
- Produces: `ToolResultSafetyInspectionFailed` is importable from `inspection/errors.py` without importing LangChain; batch and run-agent code classify it without importing the DeepAgents middleware module.

- [x] **Step 1: Add failing tests** where the outer run deadline cancels a blocked inspector; assert the safety marker propagates, `/dev/termination-log` receives only the fixed marker, and no Result CR is published. Add an import-blocking test proving `batch` and Gemini/OpenAI paths can load with DeepAgents/LangChain unavailable.
- [x] **Step 2: Run** focused `tests/test_run_agent.py`, `tests/test_batch.py`, and `tests/test_optional_provider_imports.py`; confirm blocked-inspector cancellation remains a safety marker and optional imports are blocked.
- [x] **Step 3: Move** the marker class to `inspection/errors.py`; update middleware, provider, batch, and run-agent imports. Make package exports lazy so marker import does not load LangChain. Ensure `CancelledError` from inspection maps to the safety marker while unrelated provider timeouts keep existing behavior.
- [x] **Step 4: Run** the focused tests; safety termination and optional-provider import tests pass.
- [x] **Step 5: Commit** the safe-marker/import fix with an `OLS-4212` commit subject.

### Task 6: Full verification and single-commit preparation

**Files:**
- Review all files changed by Tasks 1–5; modify tests only if verification exposes a gap.

**Interfaces:**
- Consumes: all prior task implementations and their regression tests.
- Produces: a clean, fully verified OLS-4212 change, squashed to one commit before any push. Cluster checks are separate and require explicit cluster authorization plus a rebuilt image.

- [x] **Step 1: Run** `make verify` and `make test` in the OLS-4212 worktree; record the exact results.
- [x] **Step 2: Review** the complete diff against the merged specifications. Check that rejected content cannot reach model context, `ToolResultEvent`, logs, traces, audit events, Result CRs, or termination messages, and that passing results preserve the approved full-fidelity audit path.
- [x] **Step 3: Check** `git diff --check` and ensure only intended OLS-4212 files are changed.
- [x] **Step 4: Squash** all OLS-4212 commits, including the design note, into one commit; verify clean status and the final commit diff.
- [x] **Step 5: Report** local verification and remaining cluster-validation requirements without claiming validation for a build that has not been deployed.
