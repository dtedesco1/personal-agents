"""
Unit tests focused on stable, internal behavior (no external deps):
- ToolSpec derivation and validation
- Registration with a fake FastMCP-like object (no real fastmcp import)
- Ensure validation rejects varargs, missing returns, and bad exclude_args

These tests are hermetic and do not rely on exa-py or network.
"""
from __future__ import annotations

import types
import pytest

from mcp_servers.tooling import (
    ToolSpec,
    tool_meta,
    ensure_no_varargs,
    ensure_return_annotation,
    ensure_exclude_args_valid,
    derive_toolspec_from_fn,
    register_spec_with_fastmcp,
)


def test_toolspec_effective_name_from_fn_name() -> None:
    def ok(a: int) -> int:
        return a + 1

    spec = ToolSpec(func=ok)
    assert spec.effective_name() == "ok"


def test_derive_toolspec_from_fn_with_metadata() -> None:
    @tool_meta(name="custom", description="desc")
    def fn(x: int) -> int:
        return x

    spec = derive_toolspec_from_fn(fn)
    assert spec.name == "custom"
    assert spec.description == "desc"


def test_validation_rejects_varargs_and_missing_return() -> None:
    def bad1(*args) -> int:
        return 1

    with pytest.raises(ValueError):
        ensure_no_varargs(bad1)

    def bad2(x: int):
        pass

    with pytest.raises(ValueError):
        ensure_return_annotation(bad2)


def test_validation_exclude_args_must_be_optional() -> None:
    def ok(x: int, y: int = 1) -> int:
        return x + y

    # Invalid: excludes required
    with pytest.raises(ValueError):
        ensure_exclude_args_valid(ok, ["x"])

    # Valid: excludes optional
    ensure_exclude_args_valid(ok, ["y"])  # no raise


def test_register_spec_with_fake_mcp_rejects_dupes() -> None:
    # Fake MCP with minimal tool() returning an object with name attr
    calls = []

    class FakeTool:
        def __init__(self, name: str):
            self.name = name

    class FakeMCP:
        def tool(self, fn, *, name, description=None, tags=None, annotations=None, exclude_args=None, output_schema=None, enabled=None, meta=None):
            calls.append((fn, name))
            return FakeTool(name)

    def a(x: int) -> int: return x
    def b(x: int) -> int: return x

    seen = set()
    mcp = FakeMCP()

    t1 = ToolSpec(func=a, name="foo")
    obj1 = register_spec_with_fastmcp(mcp, t1, seen_names=seen)
    assert obj1.name == "foo"

    t2 = ToolSpec(func=b, name="foo")
    with pytest.raises(ValueError, match="Duplicate tool name"):
        register_spec_with_fastmcp(mcp, t2, seen_names=seen)

