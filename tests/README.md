# Tests

Stable, hermetic tests for MCP servers and tools.

## How to run

We use uvx to resolve test deps on the fly; no project venv required.

```bash
uvx --with fastmcp --with pytest-asyncio --with pytest-timeout pytest -q
```

## What’s covered

- Tooling validation (ToolSpec, decorators, duplicate-names, signature checks)
- Server env loading from .env at startup (no per-tool dotenv)
- Dynamic tool discovery + error capture for broken modules
- Minimal MCP server smoke using FastMCP Client (admin tools always present)

## Principles

- No external network calls; tests do not require provider API keys
- When optional SDKs are present, tests may verify additional tool names are registered
- Keep tests readable and fast; prefer simple invariants and clear failures
