"""
Generic MCP server that dynamically discovers tools from tools/ and registers
them with FastMCP. Authoring is by convention, no server edits required.

Discovery precedence per module (first match wins):
  1) register(mcp): module handles full control
  2) TOOL_SPECS: list[ToolSpec]
  3) TOOLS: list[callable]
  4) Fallback: functions with @tool_meta or names starting with 'tool_'

Strict validation (hard-fail on startup):
  - Duplicate tool names
  - *args/**kwargs in tool signatures
  - Missing or Any return annotation
  - Invalid exclude_args (must refer to optional parameters)

Admin tools:
  - list_loaded_tools() -> dict: JSON inventory of registered tools
  - reload_tools() -> dict: Rescan tools/ and reconcile adds/removes

Notes
  - Exa-specific behaviors (e.g., lookback defaults) belong in tools/exa_tools.py
    and not in this server. Keep this layer generic.
"""
from __future__ import annotations

import importlib
import inspect
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from fastmcp import FastMCP, Context

# ----------------------------------------------------------------------------
# Load environment from .env once at server startup
# ----------------------------------------------------------------------------
_ENV_LOADED = False

def _load_env_from_dotenv_once() -> None:
    """Load environment variables from a .env file if present.

    Preference order:
    1) python-dotenv (if installed), attempting CWD, then project root
    2) Tiny fallback parser that supports simple KEY=VALUE lines
    This runs only once per server process to avoid overhead.
    """
    import os
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    try:
        from dotenv import load_dotenv  # type: ignore
        # 1) Try current working directory
        loaded = load_dotenv()
        if not loaded:
            # 2) Try project root where this file lives
            proj_env = PROJECT_ROOT / ".env"
            if proj_env.exists():
                load_dotenv(proj_env)
    except Exception:
        # Fallback: minimal parser
        from pathlib import Path as _P
        candidates = [_P.cwd() / ".env", PROJECT_ROOT / ".env"]
        for p in candidates:
            try:
                if not p.exists():
                    continue
                for line in p.read_text().splitlines():
                    s = line.strip()
                    if not s or s.startswith("#") or "=" not in s:
                        continue
                    k, v = s.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v
                break
            except Exception:
                pass
    _ENV_LOADED = True

# Make project root importable so 'tools' resolves from any CWD
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcp_servers.tooling import (
    ToolSpec,
    derive_toolspec_from_fn,
    extract_meta,
    register_spec_with_fastmcp,
)

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="[generic_mcp] %(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Quick diagnostics to confirm interpreter and env when launched by OpenCode
import os, sys
logger.info("Python exec: %s", sys.executable)
logger.info("EXA_API_KEY set: %s", bool(os.getenv("EXA_API_KEY")))


# ----------------------------------------------------------------------------
# Server
# ----------------------------------------------------------------------------
# Enforce hard error on duplicates at FastMCP level as well
mcp = FastMCP("personal", on_duplicate_tools="error")


# Inventory for introspection (populated during registration)
_REGISTERED: Dict[str, Dict[str, Any]] = {}
_SEEN_NAMES: Set[str] = set()


TOOLS_DIR = PROJECT_ROOT / "tools"


def _iter_tool_modules() -> List[Tuple[str, str]]:
    """Yield (module_name, file_path) for importable python files in tools/.

    Skips files starting with '_' and non-.py files.
    """
    modules: List[Tuple[str, str]] = []
    if not TOOLS_DIR.exists():
        logger.warning("tools/ directory not found at %s", TOOLS_DIR)
        return modules
    for p in sorted(TOOLS_DIR.iterdir()):
        if not p.is_file():
            continue
        if p.suffix != ".py":
            continue
        if p.name.startswith("_"):
            continue
        mod_name = f"tools.{p.stem}"
        modules.append((mod_name, str(p)))
    return modules


def _register_from_module(mod: Any) -> List[str]:
    """Register tools from a single module using precedence rules.

    Returns list of tool names registered from this module.
    """
    created: List[str] = []

    # 1) register(mcp)
    if hasattr(mod, "register") and callable(mod.register):
        logger.info("Registering via %s.register(mcp)", getattr(mod, "__name__", mod))
        mod.register(mcp)
        return created

    # 2) TOOL_SPECS
    if hasattr(mod, "TOOL_SPECS") and isinstance(mod.TOOL_SPECS, list):
        for spec in mod.TOOL_SPECS:
            if not isinstance(spec, ToolSpec):
                raise ValueError(f"{mod.__name__}.TOOL_SPECS must contain ToolSpec instances")
            tool_obj = register_spec_with_fastmcp(mcp, spec, seen_names=_SEEN_NAMES)
            created.append(tool_obj.name)
        return created

    # 3) TOOLS
    if hasattr(mod, "TOOLS") and isinstance(mod.TOOLS, list):
        for fn in mod.TOOLS:
            if not callable(fn):
                raise ValueError(f"{mod.__name__}.TOOLS must contain callables")
            spec = derive_toolspec_from_fn(fn)
            tool_obj = register_spec_with_fastmcp(mcp, spec, seen_names=_SEEN_NAMES)
            created.append(tool_obj.name)
        return created

    # 4) Fallback: scan top-level functions with @tool_meta or name startswith 'tool_'
    for name, obj in inspect.getmembers(mod, inspect.isfunction):
        if obj.__module__ != mod.__name__:
            continue  # skip imported symbols
        meta = extract_meta(obj)
        if meta or name.startswith("tool_"):
            spec = derive_toolspec_from_fn(obj)
            tool_obj = register_spec_with_fastmcp(mcp, spec, seen_names=_SEEN_NAMES)
            created.append(tool_obj.name)

    return created


def load_all_tools() -> Dict[str, Any]:
    """Import all modules and register their tools."""
    _SEEN_NAMES.clear()
    errors: List[str] = []

    # Ensure 'tools' is importable as a package (not strictly required but helpful)
    tools_pkg = "tools"
    try:
        importlib.import_module(tools_pkg)
    except Exception:
        # It's fine if tools/ lacks __init__.py; module imports by path will still work
        pass

    for mod_name, _ in _iter_tool_modules():
        try:
            if mod_name in sys.modules:
                del sys.modules[mod_name]
            mod = importlib.import_module(mod_name)
            logger.info("Discovered module: %s", mod_name)
            _register_from_module(mod)
        except Exception as e:
            logger.error("Failed to register tools from %s: %s", mod_name, e, exc_info=True)
            errors.append(f"{mod_name}: {e}")

    # Build a small inventory from _SEEN_NAMES; FastMCP will expose details to clients
    tools_list = sorted(_SEEN_NAMES)
    summary = {"registered": tools_list, "count": len(tools_list), "errors": errors}
    logger.info("Tool load summary: %s", summary)
    return summary


# Eagerly load on startup
_load_env_from_dotenv_once()
LOAD_SUMMARY = load_all_tools()


@mcp.tool(name="list_loaded_tools", annotations={"title": "List Loaded Tools", "readOnlyHint": True})
async def list_loaded_tools(ctx: Context | None = None) -> Dict[str, Any]:
    """Return inventory of all currently registered tools as structured JSON."""
    return {"tools": [{"name": n} for n in sorted(_SEEN_NAMES)], "count": len(_SEEN_NAMES), "load_summary": LOAD_SUMMARY}


@mcp.tool(name="reload_tools", annotations={"title": "Reload Tools"})
async def reload_tools(ctx: Context | None = None) -> Dict[str, Any]:
    """Rescan tools/ and reconcile the tool set. Returns new inventory summary."""
    _SEEN_NAMES.clear()
    summary = load_all_tools()
    return {"reloaded": True, "summary": summary}


if __name__ == "__main__":
    logger.info("Starting Generic Tool Server (MCP/stdio)…")
    mcp.run()

