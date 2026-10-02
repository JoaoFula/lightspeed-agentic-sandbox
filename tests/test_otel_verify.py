"""Unit tests for OTEL evidence predicates."""

from __future__ import annotations

from tests.e2e.otel_verify import (
    logs_contain_audit_logs_for_run,
    logs_contain_tool_result_inspection_for_run,
    logs_contain_traces_for_run,
)


class TestOtelVerify:
    RUN_UID = "a" * 32

    def test_traces_positive(self) -> None:
        logs = f"ResourceSpans #0\nSpan #0\n     -> agenticrun.uid: Str({self.RUN_UID})"
        assert logs_contain_traces_for_run(logs, self.RUN_UID)

    def test_traces_negative_without_span_markers(self) -> None:
        logs = f"agenticrun.uid={self.RUN_UID}"
        assert not logs_contain_traces_for_run(logs, self.RUN_UID)

    def test_audit_logs_positive(self) -> None:
        logs = (
            "LogsExporter\nLogRecord #0\n"
            f"     -> agenticrun.uid: Str({self.RUN_UID})\n"
            "     -> agenticrun.phase: Str(analysis)\n"
            "     -> event: Str(gen_ai.choice)"
        )
        assert logs_contain_audit_logs_for_run(logs, self.RUN_UID, phase="analysis")

    def test_audit_logs_negative_wrong_phase(self) -> None:
        logs = (
            "LogsExporter\nLogRecord #0\n"
            f"     -> agenticrun.uid: Str({self.RUN_UID})\n"
            "     -> agenticrun.phase: Str(execution)\n"
            "     -> event: Str(gen_ai.choice)"
        )
        assert not logs_contain_audit_logs_for_run(logs, self.RUN_UID, phase="analysis")

    def test_tool_result_inspection_positive(self) -> None:
        logs = (
            "ResourceSpans #0\n"
            "Span #0\n"
            f"     -> agenticrun.uid: Str({self.RUN_UID})\n"
            "[pod/otel-collector/otel-collector] 2026-10-02T19:15:25.104289208Z "
            "Trace ID       : shared-trace\n"
            "Span #1\n"
            "    Name           : tool_result.inspection\n"
            "     -> inspection.outcome: Str(benign)\n"
            "[pod/otel-collector/otel-collector] 2026-10-02T19:15:25.104289208Z "
            "Trace ID       : shared-trace\n"
        )
        assert logs_contain_tool_result_inspection_for_run(logs, self.RUN_UID)

    def test_tool_result_inspection_accepts_expected_malicious_outcome(self) -> None:
        logs = (
            "Span #0\n"
            f"     -> agenticrun.uid: Str({self.RUN_UID})\n"
            "Trace ID       : malicious-trace\n"
            "Span #1\n"
            "    Name           : tool_result.inspection\n"
            "     -> inspection.outcome: Str(malicious)\n"
            "Trace ID       : malicious-trace\n"
        )
        assert logs_contain_tool_result_inspection_for_run(
            logs,
            self.RUN_UID,
            expected_outcome="malicious",
        )

    def test_tool_result_inspection_rejects_non_benign_outcome(self) -> None:
        logs = (
            "ResourceSpans #0\n"
            "Span #0\n"
            f"     -> agenticrun.uid: Str({self.RUN_UID})\n"
            "Trace ID       : shared-trace\n"
            "Span #1\n"
            "    Name           : tool_result.inspection\n"
            "     -> inspection.outcome: Str(classifier_error)\n"
            "Trace ID       : shared-trace\n"
        )
        assert not logs_contain_tool_result_inspection_for_run(logs, self.RUN_UID)

    def test_tool_result_inspection_rejects_inspection_span_from_another_trace(self) -> None:
        logs = (
            "ResourceSpans #0\n"
            "Span #0\n"
            f"     -> agenticrun.uid: Str({self.RUN_UID})\n"
            "Trace ID       : run-trace\n"
            "Span #1\n"
            "    Name           : tool_result.inspection\n"
            "Trace ID       : other-trace\n"
        )
        assert not logs_contain_tool_result_inspection_for_run(logs, self.RUN_UID)
