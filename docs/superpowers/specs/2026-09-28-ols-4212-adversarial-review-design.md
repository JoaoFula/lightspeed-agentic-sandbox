# OLS-4212 Adversarial Review Remediation Design

## Goal

Close the adversarial-review gaps in the DeepAgents tool-result inspection implementation while preserving the existing `task` subagent capability. Conform to the merged OLS-3928 specifications, especially the distinction between payload-free developer/inspection telemetry and full-fidelity audit events for results that pass inspection.

## Scope

Address these findings in the existing OLS-4212 change:

1. Results from the built-in general-purpose `task` subagent are not inspected inside that subagent before its model sees them.
2. Parent middleware misses `Command` results that contain model-visible `ToolMessage` values.
3. Inspection currently occurs before DeepAgents filesystem result offload, rather than on the effective model-visible result.
4. Contradictory or extra classifier response fields can be accepted as benign; mixed text/refusal responses need fail-closed validation.
5. UTF-8 byte-based chunk boundaries can split a multibyte character and fail benign inspection.
6. An outer agent deadline can mask inspection cancellation as a generic timeout instead of the safety marker.
7. The module-level `batch.py` import of inspection middleware breaks optional-provider isolation.
8. DeepAgents developer logging must not include tool arguments/results/errors. Only a result that passes inspection may enter the approved full-fidelity AuditLogger content path; rejected results must not enter it.

## Intended Design

- Preserve `task` by supplying an explicit general-purpose subagent configuration to `create_deep_agent`, with the same inspection policy installed in its middleware stack. Keep its tools, role, and user-visible purpose equivalent to the current default.
- Move the enforcement boundary to the final model-input path so it sees tool messages after filesystem offload or other middleware transformations. Inspect only newly model-visible tool-result messages, including values nested in `Command` state updates; fail before invoking that model. Rejected content must never be forwarded or emitted as a result event.
- Apply the same model-input inspection boundary to the main agent and its general-purpose subagent. Inspecting a subagent's returned report again at the parent boundary is acceptable and provides defense in depth.
- Keep normalization and result-event emission downstream of successful inspection. EventLogger receives only controlled, payload-free DeepAgents tool metadata. AuditLogger receives the complete normalized result only after inspection passes. A failure emits no tool-result event to either logger.
- Enforce a strict classifier response contract: reject refusals, extra fields, malformed envelopes, and inconsistent decision/category fields. Treat any invalid or contradictory response as classifier failure.
- Make chunk slicing UTF-8 safe while preserving complete input coverage and overlap semantics. Do not truncate inspection input.
- Preserve fail-closed behavior under deadline cancellation: an inspection interrupted by the initiating run deadline must become `ToolResultSafetyInspectionFailed`, with no rejected result or classifier detail exposed.
- Keep DeepAgents/LangChain imports lazy on Gemini/OpenAI paths. The fixed safety marker must remain importable by `batch.py` without importing optional DeepAgents dependencies.

## Error and Data-Handling Rules

- Inspection setup, provider, parsing, refusal, timeout, and safety-detection failures stop the tool/model loop.
- The safety marker remains `ToolResultSafetyInspectionFailed`; rejected content and classifier details do not enter the Result CR, termination log, developer logs, audit events, or inspection telemetry.
- A passing complete result can enter the existing approved AuditLogger content event under configured capture/export policy.
- Inspection spans/events and EventLogger records contain only controlled metadata, never tool input/output or classifier payloads.
- Existing Gemini ADK and OpenAI Agents behavior remains unchanged.

## Verification

Add offline regression tests before implementation for:

- benign and malicious `ToolMessage` results returned directly and inside `Command.update["messages"]`;
- model-call interception after filesystem offload, including a result changed to an offload preview/reference;
- an explicit `task` subagent whose tool result is rejected before its next model call, and a rejected task report suppressed at the parent;
- accepted full-fidelity AuditLogger events versus payload-free EventLogger and inspection telemetry;
- strict refusal, extra-field, contradictory-field, malformed-envelope, and valid-decision classifier responses;
- multibyte UTF-8 text at chunk boundaries and complete input reconstruction;
- deadline cancellation producing the safety marker and batch Result CR suppression;
- importing batch/using Gemini or OpenAI paths without DeepAgents installed.

Run the existing `make verify` and `make test` checks. Cluster validation must use a rebuilt image with a new Git build marker; prior cluster results for `574847f` do not validate the remediation.

## Alternatives Considered

- Disable `task`: closes the subagent path but removes an existing DeepAgents capability. Rejected because the guard should cover available model-visible results.
- Inspect only the parent's task report: insufficient because a subagent can consume malicious tool output before producing that report.
- Keep tool-call middleware and only unwrap `Command`: insufficient because filesystem middleware transforms results after the user middleware returns, leaving the eventual model-visible artifact unchecked.
