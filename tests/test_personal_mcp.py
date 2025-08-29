"""
Minimal smoke tests for the 'personal' MCP server using FastMCP Client over stdio.

These tests do not call Exa APIs (no API key required). They only verify that:
- The generic server can start over stdio
- The expected tools are registered and listable (names only)

We intentionally avoid network calls. If EXA_API_KEY is set in the environment,
you can extend these tests to exercise the tool call paths.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.asyncio


async def _list_tools_via_client(server_path: str) -> list[str]:
    """Start the MCP server process via stdio and list tool names.

    Uses FastMCP Client with a local Python script as the transport target.
    """
    # Lazy import to avoid dependency when collecting tests without fastmcp installed
    from fastmcp import Client  # type: ignore

    async with Client(server_path) as client:
        tools = await client.list_tools()
        return [t.name for t in tools]


async def _find_repo_root() -> Path:
    """Resolve repository root assuming tests/ is inside the repo root."""
    here = Path(__file__).resolve()
    return here.parent.parent


@pytest.mark.timeout(30)
async def test_generic_server_lists_tools_names_only() -> None:
    """The generic server should start and list tools.

    This test is stable without exa-py: it only requires the server to start and
    the admin tools to be present. If exa-py is available in the environment,
    we additionally assert the Exa tool names.
    """
    repo = await _find_repo_root()
    server = repo / "mcp_servers" / "generic_server.py"
    assert server.exists(), f"Missing server file: {server}"

    names = await _list_tools_via_client(str(server))

    # Admin tools should always be present
    for expected in ("list_loaded_tools", "reload_tools"):
        assert expected in names, f"Expected admin tool '{expected}' not found in {names}"

    # If exa-py is importable in this runtime, the Exa tools should be registered
    try:
        import importlib.util as _i
        has_exa = _i.find_spec("exa_py") is not None
    except Exception:
        has_exa = False
    if has_exa:
        for expected in ("wide_search", "deep_search"):
            assert expected in names, f"Expected tool '{expected}' not found in {names}"



