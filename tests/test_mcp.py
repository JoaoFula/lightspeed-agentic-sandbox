"""Tests for MCP server configuration parsing and provider adapters."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from lightspeed_agentic.mcp import (
    MCPConfigError,
    ResolvedMCPHeader,
    ResolvedMCPServer,
    parse_mcp_servers,
    to_gemini_mcp_toolsets,
    to_openai_mcp_servers,
)


class TestParseMCPServers:
    def test_empty_env_returns_empty(self):
        with patch.dict(os.environ, {}, clear=True):
            assert parse_mcp_servers() == []

    def test_empty_string_returns_empty(self):
        with patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": ""}):
            assert parse_mcp_servers() == []

    def test_whitespace_returns_empty(self):
        with patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": "   "}):
            assert parse_mcp_servers() == []

    def test_invalid_json_raises(self):
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": "not-json"}),
            pytest.raises(MCPConfigError, match="invalid JSON"),
        ):
            parse_mcp_servers()

    def test_non_array_raises(self):
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": '{"key": "val"}'}),
            pytest.raises(MCPConfigError, match="must be a JSON array"),
        ):
            parse_mcp_servers()

    def test_basic_server_no_headers(self):
        servers_json = json.dumps([{"name": "test", "url": "http://test:8080/mcp"}])
        with patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}):
            result = parse_mcp_servers()
            assert len(result) == 1
            assert result[0] == ResolvedMCPServer(
                name="test", url="http://test:8080/mcp", timeout=60, headers=[]
            )

    def test_custom_timeout(self):
        servers_json = json.dumps([{"name": "test", "url": "http://test:8080/mcp", "timeout": 120}])
        with patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}):
            result = parse_mcp_servers()
            assert result[0].timeout == 120

    def test_service_account_token_header(self, tmp_path: Path):
        token_file = tmp_path / "token"
        token_file.write_text("my-sa-token")

        servers_json = json.dumps(
            [
                {
                    "name": "ocp",
                    "url": "http://mcp:8080/mcp",
                    "headers": [{"name": "Authorization", "source": "ServiceAccountToken"}],
                }
            ]
        )
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}),
            patch("lightspeed_agentic.mcp.SA_TOKEN_PATH", str(token_file)),
        ):
            result = parse_mcp_servers()
            assert len(result) == 1
            assert result[0].headers == [
                ResolvedMCPHeader(name="Authorization", value="Bearer my-sa-token")
            ]

    def test_service_account_token_missing(self):
        servers_json = json.dumps(
            [
                {
                    "name": "ocp",
                    "url": "http://mcp:8080/mcp",
                    "headers": [{"name": "Authorization", "source": "ServiceAccountToken"}],
                }
            ]
        )
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}),
            patch("lightspeed_agentic.mcp.SA_TOKEN_PATH", "/nonexistent/path"),
        ):
            result = parse_mcp_servers()
            assert len(result) == 1
            assert result[0].headers == []

    def test_secret_header(self, tmp_path: Path):
        secret_dir = tmp_path / "my-secret"
        secret_dir.mkdir()
        (secret_dir / "header").write_text("secret-value-123")

        servers_json = json.dumps(
            [
                {
                    "name": "ext",
                    "url": "http://ext:9090/mcp",
                    "headers": [
                        {"name": "X-Api-Key", "source": "Secret", "secretName": "my-secret"}
                    ],
                }
            ]
        )
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}),
            patch("lightspeed_agentic.mcp.MCP_SECRET_MOUNT_ROOT", str(tmp_path)),
        ):
            result = parse_mcp_servers()
            assert result[0].headers == [
                ResolvedMCPHeader(name="X-Api-Key", value="secret-value-123")
            ]

    def test_secret_dir_missing(self):
        servers_json = json.dumps(
            [
                {
                    "name": "ext",
                    "url": "http://ext:9090/mcp",
                    "headers": [
                        {"name": "X-Api-Key", "source": "Secret", "secretName": "no-such-secret"}
                    ],
                }
            ]
        )
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}),
            patch("lightspeed_agentic.mcp.MCP_SECRET_MOUNT_ROOT", "/nonexistent"),
        ):
            result = parse_mcp_servers()
            assert result[0].headers == []

    def test_client_source_skipped(self):
        servers_json = json.dumps(
            [
                {
                    "name": "ext",
                    "url": "http://ext:9090/mcp",
                    "headers": [{"name": "Authorization", "source": "Client"}],
                }
            ]
        )
        with patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}):
            result = parse_mcp_servers()
            assert result[0].headers == []

    def test_multiple_servers(self, tmp_path: Path):
        token_file = tmp_path / "token"
        token_file.write_text("tok")

        servers_json = json.dumps(
            [
                {"name": "a", "url": "http://a:8080/mcp"},
                {"name": "b", "url": "http://b:8080/mcp", "timeout": 30},
            ]
        )
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}),
            patch("lightspeed_agentic.mcp.SA_TOKEN_PATH", str(token_file)),
        ):
            result = parse_mcp_servers()
            assert len(result) == 2
            assert result[0].name == "a"
            assert result[1].name == "b"
            assert result[1].timeout == 30

    def test_invalid_entry_raises(self):
        servers_json = json.dumps([42, {"name": "ok", "url": "http://ok:8080/mcp"}])
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}),
            pytest.raises(MCPConfigError, match=r"\[0\] must be a JSON object"),
        ):
            parse_mcp_servers()

    def test_invalid_header_raises(self):
        servers_json = json.dumps(
            [
                {
                    "name": "s",
                    "url": "http://s:8080/mcp",
                    "headers": [
                        "bad",
                        {"name": "X", "source": "Client"},
                    ],
                },
            ]
        )
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}),
            pytest.raises(MCPConfigError, match=r"headers\[0\] must be a JSON object"),
        ):
            parse_mcp_servers()

    def test_unknown_header_source_raises(self):
        servers_json = json.dumps(
            [
                {
                    "name": "s",
                    "url": "http://s:8080/mcp",
                    "headers": [{"name": "X", "source": "Unknown"}],
                },
            ]
        )
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}),
            pytest.raises(MCPConfigError, match="unsupported source"),
        ):
            parse_mcp_servers()

    def test_path_traversal_rejected(self, tmp_path: Path):
        mount_root = tmp_path / "secrets"
        mount_root.mkdir()
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        (outside_dir / "leaked").write_text("should-not-be-read")

        servers_json = json.dumps(
            [
                {
                    "name": "evil",
                    "url": "http://x:8080/mcp",
                    "headers": [
                        {"name": "X", "source": "Secret", "secretName": "../outside"},
                    ],
                },
            ]
        )
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}),
            patch("lightspeed_agentic.mcp.MCP_SECRET_MOUNT_ROOT", str(mount_root)),
        ):
            result = parse_mcp_servers()
            assert result[0].headers == []

    def test_headers_null_treated_as_empty(self):
        servers_json = json.dumps(
            [
                {"name": "s", "url": "http://s:8080/mcp", "headers": None},
            ]
        )
        with patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}):
            result = parse_mcp_servers()
            assert result[0].headers == []

    def test_headers_non_list_raises(self):
        servers_json = json.dumps(
            [
                {"name": "s", "url": "http://s:8080/mcp", "headers": "bad"},
            ]
        )
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}),
            pytest.raises(MCPConfigError, match="headers must be a JSON array"),
        ):
            parse_mcp_servers()

    def test_header_non_string_name_raises(self):
        servers_json = json.dumps(
            [
                {
                    "name": "s",
                    "url": "http://s:8080/mcp",
                    "headers": [{"name": 42, "source": "Client"}],
                },
            ]
        )
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}),
            pytest.raises(MCPConfigError, match=r"headers\[0\] missing or invalid name"),
        ):
            parse_mcp_servers()

    def test_header_empty_name_raises(self):
        servers_json = json.dumps(
            [
                {
                    "name": "s",
                    "url": "http://s:8080/mcp",
                    "headers": [{"name": "", "source": "Client"}],
                },
            ]
        )
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}),
            pytest.raises(MCPConfigError, match=r"headers\[0\] missing or invalid name"),
        ):
            parse_mcp_servers()

    def test_header_non_string_source_raises(self):
        servers_json = json.dumps(
            [
                {
                    "name": "s",
                    "url": "http://s:8080/mcp",
                    "headers": [{"name": "X", "source": 123}],
                },
            ]
        )
        with (
            patch.dict(os.environ, {"LIGHTSPEED_MCP_SERVERS": servers_json}),
            pytest.raises(MCPConfigError, match=r"headers\[0\] missing or invalid source"),
        ):
            parse_mcp_servers()


class TestGeminiAdapter:
    def test_creates_toolsets(self):
        servers = [ResolvedMCPServer(name="ocp-mcp", url="https://ocp:8443/mcp", timeout=90)]
        toolsets = to_gemini_mcp_toolsets(servers)
        assert len(toolsets) == 1
        from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

        assert isinstance(toolsets[0], McpToolset)

    def test_passes_connection_params(self):
        servers = [
            ResolvedMCPServer(
                name="s",
                url="http://test:8080/mcp",
                timeout=45,
                headers=[ResolvedMCPHeader(name="X-Key", value="val")],
            )
        ]
        toolsets = to_gemini_mcp_toolsets(servers)
        params = toolsets[0]._connection_params
        assert params.url == "http://test:8080/mcp"
        assert params.headers == {"X-Key": "val"}
        assert params.timeout == 45.0
        assert callable(params.httpx_client_factory)


class TestOpenAIAdapter:
    def test_creates_servers(self) -> None:
        servers = [ResolvedMCPServer(name="ocp-mcp", url="https://ocp:8443/mcp")]
        result = to_openai_mcp_servers(servers)
        assert len(result) == 1
        from agents.mcp import MCPServerStreamableHttp

        assert isinstance(result[0], MCPServerStreamableHttp)
        assert result[0].name == "ocp-mcp"
        assert "httpx_client_factory" in result[0].params

    def test_passes_headers(self) -> None:
        servers = [
            ResolvedMCPServer(
                name="ext",
                url="http://ext/mcp",
                headers=[ResolvedMCPHeader(name="Auth", value="Bearer x")],
            )
        ]
        result = to_openai_mcp_servers(servers)
        assert result[0].params["headers"] == {"Auth": "Bearer x"}
        assert "httpx_client_factory" in result[0].params
