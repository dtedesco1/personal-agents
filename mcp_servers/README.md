# MCP Servers

## Purpose
<!-- readme:purpose-start -->
MCP servers for this repo. Each server exposes a small, well‑named tool surface to the agents (stdio transport), wrapping code that lives in tools/. Servers must be easy to swap and trivial to smoke‑test.
<!-- readme:purpose-end -->

## Architecture
<!-- readme:architecture-start -->
StdIO Model Context Protocol (MCP) servers implemented with FastMCP. OpenCode spawns them based on opencode.json.

```mermaid
flowchart LR
  Agent -->|calls tool| OpenCode
  OpenCode -->|spawn stdio| MCP_Server
  MCP_Server -->|import| tools_pkg
  tools_pkg -->|vendor SDK/API| External
```

Key points:

- Transport: stdio (no HTTP daemon)
- Library: fastmcp (Python)
- Server object: FastMCP("ServerName") with @mcp.tool functions
- .env is loaded once at server startup; do not load env in tools/
- Wiring: opencode.json → mcp.{name}.command typically uses uvx to resolve deps
<!-- readme:architecture-end -->

### Contents
<!-- readme:contents-start -->
```text
mcp_servers/
├── generic_server.py    # Discovers tools/* and registers them dynamically
├── tooling.py           # ToolSpec/decorators/validation helpers for tools/
└── README.md            # This file
```
<!-- readme:contents-end -->

### Doc Refs
<!-- readme:doc-refs-start -->
- opencode.json – MCP server process config used by OpenCode
- tools/README.md – where underlying implementations live and conventions
- .opencode/agent/single-newsletter-agent.md – how agents are expected to use tools
- FastMCP docs: <https://gofastmcp.com> (run servers, Client usage, stdio)
<!-- readme:doc-refs-end -->

### Test Refs
<!-- readme:test-refs-start -->
Manual smoke (no project installs):

- List tools via Client (verifies server starts + registers tools)

  uvx --with fastmcp python - << 'PY'
  import asyncio
  from fastmcp import Client
  async def main():
      client = Client("mcp_servers/generic_server.py")
      async with client:
          tools = await client.list_tools()
          print("TOOLS:", [t.name for t in tools])
  asyncio.run(main())
  PY

- Direct run via CLI (stdio server)

  uvx --with fastmcp fastmcp run mcp_servers/generic_server.py:mcp

When calling tools that depend on external services, ensure required env keys are present in .env.
<!-- readme:test-refs-end -->

### Examples
<!-- readme:examples-start -->
Add a new MCP server file (stdio):

```python
from fastmcp import FastMCP, Context
from tools.some_tools import do_something

mcp = FastMCP("SomeServer")

@mcp.tool(name="some_action")
async def some_action(query: str, ctx: Context | None = None) -> dict:
    ctx and await ctx.info("starting some_action")
    return do_something(query)

if __name__ == "__main__":
    mcp.run()
```

Wire it in opencode.json (use uvx to avoid global installs):

```json
{
  "mcp": {
    "some": {
      "type": "local",
      "command": [
        "uvx", "--with", "fastmcp", "--with", "<extra-pkgs>",
        "fastmcp", "run", "mcp_servers/some_server.py:mcp"
      ],
      "enabled": true,
      "environment": { "FOO_API_KEY": "..." }
    }
  }
}
```
<!-- readme:examples-end -->

### Custom Notes
<!-- readme:custom-notes-start -->
- Do not rename existing tool entry points without updating agent prompts that reference them.
- Prefer explicit, descriptive tool names (e.g., wide_search, deep_search). Avoid vague names.
- Keep servers thin; business logic belongs in tools/ so multiple servers can reuse functions.
- Always use uvx --with to resolve runtime deps when run by OpenCode. This repo avoids committing Python lockfiles here.
<!-- readme:custom-notes-end -->

## Troubleshooting (generic)

- Server interpreter
  - Confirm which Python is launching the server (opencode.json defines command)
  - For quick diagnostics, temporarily log sys.executable in the server file
- Environment
  - .env is loaded once at server startup; restart after edits
  - Keep all required keys for your tools in .env at repo root
- Tool discovery
  - Use list_loaded_tools to verify registration; missing tools often mean export pattern issues
- Imports
  - If a tool relies on a third-party package, ensure it’s available in the runtime
  - Options: configure uvx with --with PACKAGE_NAME, or point to a Python with the package installed
- Reload
  - Use reload_tools to rescan tools/ without a full restart
