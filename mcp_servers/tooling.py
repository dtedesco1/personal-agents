"""
Tooling utilities for dynamic MCP tool discovery and strict validation.

This module provides:
- ToolSpec: a dataclass for explicit tool metadata
- @tool_meta: a lightweight decorator to attach metadata to plain functions
- Validation helpers: fail fast on duplicate names, varargs, and missing return annotations

Design goals
- Keep authoring simple (no FastMCP import required in tools/ modules)
- Provide clear, actionable error messages on startup
- Centralize all validation rules so the generic server can be minimal

Authoring patterns enabled by this module
1) Plain function + optional @tool_meta in tools/*.py
2) TOOLS = [fn, ...]
3) TOOL_SPECS = [ToolSpec(...), ...]
4) register(mcp) in a tools module for full control

NOTE: This module deliberately avoids importing fastmcp at import time to
keep tools authoring lightweight. The generic server will import fastmcp and
use these helpers to construct tools with metadata.
"""
from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ToolSpec:
    """Declarative specification for a tool.

    Fields mirror common FastMCP @mcp.tool parameters, while keeping the
    authoring surface independent from FastMCP itself.
    """

    func: Callable[..., Any]
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[Set[str]] = None
    annotations: Optional[Dict[str, Any]] = None
    exclude_args: Optional[List[str]] = None
    output_schema: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None
    meta: Optional[Dict[str, Any]] = None

    def effective_name(self) -> str:
        return (self.name or getattr(self.func, "__name__", None) or "").strip()


def tool_meta(
    *,
    name: str | None = None,
    description: str | None = None,
    tags: Set[str] | None = None,
    annotations: Dict[str, Any] | None = None,
    exclude_args: List[str] | None = None,
    output_schema: Dict[str, Any] | None = None,
    enabled: bool | None = None,
    meta: Dict[str, Any] | None = None,
):
    """Attach MCP-relevant metadata to a plain function.

    This does not register the function as a tool. The generic server
    will inspect this metadata and call FastMCP appropriately.
    """

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        setattr(
            fn,
            "__tool_meta__",
            {
                "name": name,
                "description": description,
                "tags": set(tags) if tags else None,
                "annotations": annotations,
                "exclude_args": list(exclude_args) if exclude_args else None,
                "output_schema": output_schema,
                "enabled": enabled,
                "meta": meta,
            },
        )
        return fn

    return decorator


# ------------------------------
# Validation helpers
# ------------------------------

def ensure_no_varargs(fn: Callable[..., Any]) -> None:
    """Ensure function signature does not use *args/**kwargs.

    FastMCP requires a complete, explicit parameter schema.
    """
    sig = inspect.signature(fn)
    for p in sig.parameters.values():
        if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            raise ValueError(
                f"Tool '{getattr(fn, '__name__', '<unknown>')}' must not use *args/**kwargs."
            )


def ensure_return_annotation(fn: Callable[..., Any]) -> None:
    """Ensure the function has a non-empty, non-Any return annotation.

    Rationale: We want a deterministic output schema/path for clients.
    """
    ann = inspect.signature(fn).return_annotation
    if ann is inspect._empty:
        raise ValueError(
            f"Tool '{getattr(fn, '__name__', '<unknown>')}' must have a return type annotation."
        )
    # Detect typing.Any across Python versions
    try:
        from typing import Any as TypingAny  # type: ignore
        if ann is TypingAny:
            raise ValueError(
                f"Tool '{getattr(fn, '__name__', '<unknown>')}' must not use 'Any' as return annotation."
            )
    except Exception:
        # Best-effort only; if import fails we still enforced non-empty
        pass


def ensure_exclude_args_valid(fn: Callable[..., Any], exclude_args: Optional[List[str]]) -> None:
    """Ensure excluded args exist and are optional (have defaults).

    FastMCP only allows excluding arguments with default values.
    """
    if not exclude_args:
        return
    sig = inspect.signature(fn)
    for arg in exclude_args:
        if arg not in sig.parameters:
            raise ValueError(
                f"exclude_args specifies '{arg}' but it is not a parameter of tool '{getattr(fn, '__name__', '<unknown>')}'."
            )
        p = sig.parameters[arg]
        if p.default is inspect._empty:
            raise ValueError(
                f"exclude_args includes required parameter '{arg}' in tool '{getattr(fn, '__name__', '<unknown>')}'. Only optional params can be excluded."
            )


def extract_meta(fn: Callable[..., Any]) -> Dict[str, Any]:
    """Get attached metadata dict from a function if present; else {}."""
    return getattr(fn, "__tool_meta__", {}) or {}


def derive_toolspec_from_fn(fn: Callable[..., Any]) -> ToolSpec:
    """Create a ToolSpec from a function using attached metadata if any."""
    md = extract_meta(fn)
    return ToolSpec(
        func=fn,
        name=md.get("name"),
        description=md.get("description"),
        tags=md.get("tags"),
        annotations=md.get("annotations"),
        exclude_args=md.get("exclude_args"),
        output_schema=md.get("output_schema"),
        enabled=md.get("enabled"),
        meta=md.get("meta"),
    )


def validate_toolspec(spec: ToolSpec) -> None:
    """Run all validation checks on a ToolSpec's function and metadata."""
    fn = spec.func
    ensure_no_varargs(fn)
    ensure_return_annotation(fn)
    ensure_exclude_args_valid(fn, spec.exclude_args)


def register_spec_with_fastmcp(mcp: Any, spec: ToolSpec, *, seen_names: Set[str]) -> Any:
    """Register a ToolSpec with FastMCP, enforcing duplicate policy.

    Returns the created Tool (from FastMCP) for inventory purposes.
    """
    validate_toolspec(spec)
    name = spec.effective_name()
    if not name:
        raise ValueError("Tool name resolved to empty string.")
    if name in seen_names:
        raise ValueError(f"Duplicate tool name detected: '{name}'")

    # Programmatic registration via FastMCP
    tool_obj = mcp.tool(
        spec.func,
        name=name,
        description=spec.description,
        tags=spec.tags,
        annotations=spec.annotations,
        exclude_args=spec.exclude_args,
        output_schema=spec.output_schema,
        enabled=spec.enabled,
        meta=spec.meta,
    )
    seen_names.add(name)
    logger.info("Registered tool: %s", name)
    return tool_obj

