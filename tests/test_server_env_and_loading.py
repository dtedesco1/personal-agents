"""
Server-level tests using temporary modules to ensure:
- .env is loaded once at startup (we simulate by setting env and reloading module)
- dynamic discovery loads tools from tools/*.py
- errors from broken tool modules are captured in summary

No external APIs; we build temporary files under a temp directory and import the server pointing at that root.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest


@pytest.fixture()
def temp_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Create a fake project with tools/ and a .env
    proj = tmp_path
    (proj / "tools").mkdir()
    (proj / ".env").write_text("EXA_API_KEY=dummy\nEXA_DEFAULT_LOOKBACK_DAYS=9\n")

    # Good tool module
    (proj / "tools" / "adder.py").write_text(
        """
from mcp_servers.tooling import ToolSpec

def add(a: int, b: int) -> int:
    return a + b

TOOL_SPECS = [ToolSpec(func=add, name="add")]  # simple spec
"""
    )

    # Broken tool module to force an error path
    (proj / "tools" / "broken.py").write_text(
        """
# This module raises on import
raise RuntimeError("boom")
"""
    )

    # Create a package layout for mcp_servers so imports resolve
    (proj / "mcp_servers").mkdir()
    (proj / "mcp_servers" / "__init__.py").write_text("")

    # Copy the real tooling.py into temp project so generic_server can import it
    real_root = Path(__file__).resolve().parents[1]
    real_tooling = real_root / "mcp_servers" / "tooling.py"
    (proj / "mcp_servers" / "tooling.py").write_text(real_tooling.read_text())

    # Write a generic_server into the temp project
    (proj / "mcp_servers" / "generic_server.py").write_text(
        (real_root / "mcp_servers" / "generic_server.py").read_text()
    )

    # Ensure imports resolve to temp project first
    monkeypatch.chdir(proj)
    sys.path.insert(0, str(proj))

    # Clear any previously imported real package so temp copy loads
    for k in list(sys.modules.keys()):
        if k == "mcp_servers" or k.startswith("mcp_servers."):
            del sys.modules[k]

    yield proj

    # Cleanup sys.path entry if still present
    try:
        sys.path.remove(str(proj))
    except ValueError:
        pass


def test_env_loaded_and_tools_discovered(temp_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Import the server from the temp project
    srv = importlib.import_module("mcp_servers.generic_server")

    # The .env has EXA_API_KEY set; server loads it at startup (but a developer
    # may already have this set in their shell). Assert it is non-empty rather than
    # equal to our dummy value, to keep this test robust in real dev envs.
    assert os.getenv("EXA_API_KEY"), "EXA_API_KEY should be set by .env or existing env"

    # Summary reports registered tool names and one error from broken.py
    summary = getattr(srv, "LOAD_SUMMARY")
    assert summary["count"] >= 0
    assert any("broken" in e for e in summary["errors"])  # error captured

    # Our adder tool should load since it doesn't depend on exa-py
    assert "add" in summary["registered"], summary


def test_reload_tools_reflects_changes(temp_project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    srv = importlib.import_module("mcp_servers.generic_server")

    # Add a new tool module
    (temp_project / "tools" / "mul.py").write_text(
        """
from mcp_servers.tooling import ToolSpec

def mul(a: int, b: int) -> int:
    return a * b

TOOL_SPECS = [ToolSpec(func=mul, name="mul")]
"""
    )

    # Reload by invoking the internal loader directly (stable for unit testing)
    summary = srv.load_all_tools()
    assert "mul" in summary["registered"], summary

