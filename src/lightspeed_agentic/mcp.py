"""MCP server configuration parsing and header resolution.

Reads LIGHTSPEED_MCP_SERVERS env var (JSON array) and resolves header values
from Kubernetes-mounted secrets and projected service account tokens.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from lightspeed_agentic.readiness import read_first_mounted_secret_in_dir, read_mounted_secret

logger = logging.getLogger("lightspeed_agentic")

SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"  # noqa: S105
MCP_SECRET_MOUNT_ROOT = "/var/secrets/mcp"  # noqa: S105


class MCPConfigError(ValueError):
    """``LIGHTSPEED_MCP_SERVERS`` is set but not valid JSON array configuration."""


@dataclass(frozen=True)
class ResolvedMCPHeader:
    name: str
    value: str


@dataclass(frozen=True)
class ResolvedMCPServer:
    name: str
    url: str
    timeout: float = 60
    headers: list[ResolvedMCPHeader] = field(default_factory=list)


def _resolve_header(header: dict[str, str]) -> ResolvedMCPHeader | None:
    """Resolve a single header entry based on its source type.

    Returns ``None`` when the source is ``Client`` or resolution fails at
    runtime (missing mount, empty secret dir). Structural header errors MUST
    be raised by the caller before invoking this helper.
    """
    name = header["name"]
    source = header["source"]

    if source == "ServiceAccountToken":
        token = read_mounted_secret(Path(SA_TOKEN_PATH))
        if token is None:
            logger.warning("SA token not found at %s for header %s", SA_TOKEN_PATH, name)
            return None
        return ResolvedMCPHeader(name=name, value=f"Bearer {token}")

    if source == "Secret":
        secret_name = header.get("secretName", "")
        if not isinstance(secret_name, str):
            logger.warning("secretName must be a string for header %s", name)
            return None
        root = Path(MCP_SECRET_MOUNT_ROOT).resolve()
        secret_dir = (root / secret_name).resolve()
        if not secret_name or not secret_dir.is_relative_to(root):
            logger.warning("Invalid secret path: %s for header %s", secret_dir, name)
            return None
        value = read_first_mounted_secret_in_dir(secret_dir)
        if value is None:
            logger.warning("Secret dir empty or unreadable: %s for header %s", secret_dir, name)
            return None
        return ResolvedMCPHeader(name=name, value=value)

    if source == "Client":
        return None

    raise MCPConfigError(
        f"LIGHTSPEED_MCP_SERVERS header {name!r} has unsupported source {source!r}"
    )


def _parse_server_entry(entry: Any, index: int) -> ResolvedMCPServer:
    """Parse one MCP server entry from ``LIGHTSPEED_MCP_SERVERS``."""
    if not isinstance(entry, dict):
        raise MCPConfigError(
            f"LIGHTSPEED_MCP_SERVERS[{index}] must be a JSON object, got {type(entry).__name__}"
        )

    name = entry.get("name")
    if not isinstance(name, str) or not name.strip():
        raise MCPConfigError(f"LIGHTSPEED_MCP_SERVERS[{index}] missing or invalid name")

    url = entry.get("url")
    if not isinstance(url, str) or not url.strip():
        raise MCPConfigError(f"LIGHTSPEED_MCP_SERVERS[{index}] missing or invalid url")

    raw_headers = entry.get("headers")
    if raw_headers is None:
        raw_headers = []
    elif not isinstance(raw_headers, list):
        raise MCPConfigError(f"LIGHTSPEED_MCP_SERVERS[{index}] headers must be a JSON array")

    resolved_headers: list[ResolvedMCPHeader] = []
    for header_index, header in enumerate(raw_headers):
        if not isinstance(header, dict):
            raise MCPConfigError(
                f"LIGHTSPEED_MCP_SERVERS[{index}].headers[{header_index}] must be a JSON object"
            )
        if "name" not in header or "source" not in header:
            raise MCPConfigError(
                f"LIGHTSPEED_MCP_SERVERS[{index}].headers[{header_index}] "
                "must include name and source"
            )
        header_name = header["name"]
        if not isinstance(header_name, str) or not header_name.strip():
            raise MCPConfigError(
                f"LIGHTSPEED_MCP_SERVERS[{index}].headers[{header_index}] missing or invalid name"
            )
        header_source = header["source"]
        if not isinstance(header_source, str) or not header_source.strip():
            raise MCPConfigError(
                f"LIGHTSPEED_MCP_SERVERS[{index}].headers[{header_index}] missing or invalid source"
            )
        resolved = _resolve_header(header)
        if resolved is not None:
            resolved_headers.append(resolved)

    timeout = entry.get("timeout", 60)
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
        logger.warning("Invalid timeout in server %r, using default", name)
        timeout = 60

    return ResolvedMCPServer(
        name=name,
        url=url,
        timeout=timeout,
        headers=resolved_headers,
    )


def parse_mcp_servers() -> list[ResolvedMCPServer]:
    """Parse LIGHTSPEED_MCP_SERVERS env var and resolve all header values."""
    raw = os.environ.get("LIGHTSPEED_MCP_SERVERS", "").strip()
    if not raw:
        return []

    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MCPConfigError(f"LIGHTSPEED_MCP_SERVERS contains invalid JSON: {exc}") from exc

    if not isinstance(entries, list):
        raise MCPConfigError(
            f"LIGHTSPEED_MCP_SERVERS must be a JSON array, got {type(entries).__name__}"
        )

    servers: list[ResolvedMCPServer] = []
    for index, entry in enumerate(entries):
        servers.append(_parse_server_entry(entry, index))

    if servers:
        logger.info("Resolved %d MCP server(s): %s", len(servers), [s.name for s in servers])
    return servers


def _headers_dict(server: ResolvedMCPServer) -> dict[str, str]:
    return {h.name: h.value for h in server.headers}


def to_gemini_mcp_toolsets(servers: list[ResolvedMCPServer]) -> list[Any]:
    """Convert to google-adk McpToolset instances."""
    from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
    from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

    from lightspeed_agentic.tls import create_async_http_client

    toolsets: list[Any] = []
    for s in servers:
        params = StreamableHTTPConnectionParams(
            url=s.url,
            headers=_headers_dict(s) if s.headers else None,
            timeout=s.timeout,
            httpx_client_factory=create_async_http_client,
        )
        toolsets.append(McpToolset(connection_params=params))
    return toolsets


def to_openai_mcp_servers(servers: list[ResolvedMCPServer]) -> list[Any]:
    """Convert to openai-agents MCPServerStreamableHttp instances."""
    from agents.mcp import MCPServerStreamableHttp, MCPServerStreamableHttpParams

    from lightspeed_agentic.tls import create_async_http_client

    result: list[Any] = []
    for s in servers:
        params = MCPServerStreamableHttpParams(
            url=s.url,
            timeout=s.timeout,
            httpx_client_factory=create_async_http_client,
        )
        if s.headers:
            params["headers"] = _headers_dict(s)
        result.append(MCPServerStreamableHttp(params=params, name=s.name))
    return result
