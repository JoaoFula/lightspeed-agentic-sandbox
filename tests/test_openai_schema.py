"""Tests for OpenAI provider configuration and manifest building."""

import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_build_manifest_parent_of_cwd(monkeypatch: pytest.MonkeyPatch) -> None:
    """Manifest root should be cwd's parent so exec_command reaches the full workspace."""
    monkeypatch.delenv("E2E_OUTPUT_DIR", raising=False)
    from lightspeed_agentic.providers.openai import _build_manifest  # type: ignore[import-untyped]

    manifest = _build_manifest(str(Path("/app/skills").parent))
    assert manifest.root == "/app"


def test_build_manifest_without_e2e_output_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("E2E_OUTPUT_DIR", raising=False)
    from lightspeed_agentic.providers.openai import _build_manifest

    manifest = _build_manifest("/app/skills")
    assert manifest.root == "/app/skills"
    assert manifest.extra_path_grants == ()


def test_build_manifest_grants_e2e_output_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("E2E_OUTPUT_DIR", str(tmp_path))
    from lightspeed_agentic.providers.openai import _build_manifest

    manifest = _build_manifest("/app/skills")
    assert len(manifest.extra_path_grants) == 1
    grant = manifest.extra_path_grants[0]
    assert grant.path == str(tmp_path.resolve())
    assert grant.read_only is False


def test_build_manifest_skips_e2e_output_dir_outside_temp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("E2E_OUTPUT_DIR", "/etc")
    from lightspeed_agentic.providers.openai import _build_manifest

    manifest = _build_manifest("/app/skills")
    assert manifest.extra_path_grants == ()


async def _empty_stream() -> AsyncIterator[None]:
    return
    yield


def _run_openai_provider(cwd: str) -> Any:
    """Run OpenAIProvider.query() with mocked SDK internals.

    Returns (events, mock_sandbox_agent_cls) so callers can inspect both the
    emitted events and the kwargs passed to SandboxAgent.
    """
    from lightspeed_agentic.providers.openai import OpenAIProvider
    from lightspeed_agentic.types import ProviderQueryOptions  # type: ignore[import-untyped]

    mock_result = MagicMock()
    mock_result.stream_events = _empty_stream
    mock_result.final_output = ""
    mock_result.context_wrapper.usage.input_tokens = 0
    mock_result.context_wrapper.usage.output_tokens = 0

    async def _collect() -> tuple[list[Any], MagicMock]:
        with (
            patch("agents.sandbox.SandboxAgent", return_value=MagicMock()) as mock_cls,
            patch("agents.Runner.run_streamed", return_value=mock_result),
            patch("agents.models.openai_responses.OpenAIResponsesModel"),
            patch("openai.AsyncOpenAI"),
        ):
            provider = OpenAIProvider()
            options = ProviderQueryOptions(
                prompt="test",
                system_prompt="you are a test agent",
                model="gpt-4.1-mini",
                max_turns=1,
                allowed_tools=[],
                cwd=cwd,
            )
            events = [e async for e in provider.query(options)]
            return events, mock_cls

    return _collect()


@pytest.mark.asyncio
async def test_mcp_servers_are_passed_to_sandbox_agent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """MCP servers must use SandboxAgent's mcp_servers argument, not capabilities."""
    monkeypatch.delenv("E2E_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    from lightspeed_agentic.mcp import ResolvedMCPServer  # type: ignore[import-untyped]

    mcp_server = object()
    manager = MagicMock(active_servers=[mcp_server])
    manager.__aenter__ = AsyncMock(return_value=manager)
    manager.__aexit__ = AsyncMock(return_value=None)
    resolved_server = ResolvedMCPServer(name="test", url="http://mcp.test/mcp")

    from lightspeed_agentic.providers.openai import OpenAIProvider
    from lightspeed_agentic.types import ProviderQueryOptions

    mock_result = MagicMock()
    mock_result.stream_events = _empty_stream
    mock_result.final_output = ""
    mock_result.context_wrapper.usage.input_tokens = 0
    mock_result.context_wrapper.usage.output_tokens = 0

    async def collect() -> MagicMock:
        with (
            patch("agents.sandbox.SandboxAgent", return_value=MagicMock()) as mock_cls,
            patch("agents.Runner.run_streamed", return_value=mock_result),
            patch("agents.models.openai_responses.OpenAIResponsesModel"),
            patch("openai.AsyncOpenAI"),
            patch("agents.mcp.MCPServerManager", return_value=manager),
            patch(
                "lightspeed_agentic.mcp.to_openai_mcp_servers",
                return_value=[resolved_server],
            ),
        ):
            options = ProviderQueryOptions(
                prompt="test",
                system_prompt="you are a test agent",
                model="gpt-4.1-mini",
                max_turns=1,
                allowed_tools=[],
                cwd=str(tmp_path),
                mcp_servers=[resolved_server],
            )
            provider = OpenAIProvider()
            [event async for event in provider.query(options)]
            return mock_cls

    mock_cls = await collect()
    assert mock_cls.call_args.kwargs["mcp_servers"] == [mcp_server]
    assert mcp_server not in mock_cls.call_args.kwargs["capabilities"]


@pytest.mark.asyncio
async def test_skills_registered_when_skill_md_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Skills capability must be registered when a subdirectory contains SKILL.md."""
    monkeypatch.delenv("E2E_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    (tmp_path / "my-skill").mkdir()
    (tmp_path / "my-skill" / "SKILL.md").write_text("# skill")

    _, mock_cls = await _run_openai_provider(str(tmp_path))

    capabilities = mock_cls.call_args.kwargs["capabilities"]

    from agents.sandbox.capabilities import Skills

    skills_caps = [c for c in capabilities if isinstance(c, Skills)]
    assert len(skills_caps) == 1
    assert skills_caps[0].skills_path == "skills/.agents"


@pytest.mark.asyncio
async def test_skills_capability_omitted_when_no_skill_md(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Skills capability must not be registered when no SKILL.md exists under cwd."""
    monkeypatch.delenv("E2E_OUTPUT_DIR", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)

    _, mock_cls = await _run_openai_provider(str(tmp_path))

    capabilities = mock_cls.call_args.kwargs["capabilities"]

    from agents.sandbox.capabilities import Skills

    skills_caps = [c for c in capabilities if isinstance(c, Skills)]
    assert len(skills_caps) == 0


class TestExecCommandShellCoercion:
    """OLS-3257: model sends shell:bool instead of shell:string."""

    @pytest.fixture(autouse=True)
    def _init_openai(self) -> None:
        from lightspeed_agentic.providers.openai import _ensure_openai_init

        _ensure_openai_init()

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("shell_input", "expected"),
        [
            (True, None),
            (False, None),
            ("/bin/bash", "/bin/bash"),
            (None, None),
        ],
        ids=["bool-true", "bool-false", "string-path", "null"],
    )
    async def test_shell_coercion(self, shell_input: Any, expected: Any) -> None:
        from agents.sandbox.capabilities.tools.shell_tool import ExecCommandTool

        raw_input = json.dumps({"cmd": "echo hello", "shell": shell_input})
        captured: list[Any] = []
        original_run = ExecCommandTool.run

        async def mock_run(self: object, args: Any) -> str:  # noqa: ARG001
            captured.append(args.shell)
            return "ok"

        type.__setattr__(ExecCommandTool, "run", mock_run)
        try:
            tool = ExecCommandTool.__new__(ExecCommandTool)
            object.__setattr__(tool, "args_model", ExecCommandTool.args_model)
            await tool._invoke(None, raw_input)
            assert captured == [expected]
        finally:
            type.__setattr__(ExecCommandTool, "run", original_run)
