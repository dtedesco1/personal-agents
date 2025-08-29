# Personal Agents

Lightweight MCP-powered tooling for coding workflows, wired for OpenCode.

- Servers: FastMCP stdio servers under mcp_servers/
- Tools: Business logic under tools/
- Client: OpenCode (CLI/TUI) reads opencode.json and spawns MCP servers

## Environment loading

- .env is loaded once at MCP server startup (no per-tool dotenv code)
- Place required API keys and settings for your tools in .env at the repo root

## Quick start

1) List tools via FastMCP Client (no API calls)

```bash
uvx --with fastmcp python - <<'PY'
import asyncio
from fastmcp import Client
async def main():
    async with Client("mcp_servers/generic_server.py") as c:
        tools = await c.list_tools()
        print([t.name for t in tools])
asyncio.run(main())
PY
```

1) Run via OpenCode (personal server) and list

```bash
OPENCODE_CONFIG=./opencode.json \
  opencode run --model google/gemini-2.5-flash \
  "Call personal/list_loaded_tools and return only the JSON."
```

1) Call optional search or data tools

- Ensure any required third-party packages are importable in the server runtime
- Alternatively, use uvx and add --with PACKAGE_NAME in opencode.json

Example OpenCode prompt:

"Use personal_wide_search for 'latest AI regulation updates' with lookback_days=null. Return only a JSON with titles[] and urls[]."

## Adding tools

Write tools in tools/*.py using any of these patterns (no server edits):

- @tool_meta on plain functions
- TOOLS = [fn, ...]
- TOOL_SPECS = [ToolSpec(...), ...]
- register(mcp) for full control

See mcp_servers/tooling.py for decorator, ToolSpec, and validation rules.

## Tests

- Hermetic unit tests (no external network) live in tests/
- Run: uvx --with fastmcp --with pytest-asyncio --with pytest-timeout pytest -q

## Configuration (OpenCode)

- The personal MCP server is configured in opencode.json
- To guarantee required packages are available within OpenCode, either:
  - Use uvx with --with PACKAGE_NAME (see opencode.json), or
  - Point command to a Python interpreter that has the package installed

## Notes

- Keep business logic in tools/; keep servers thin
- Avoid network calls in unit tests

## Troubleshooting (generic)

- Verify server interpreter
  - Ensure the MCP server is launched with the Python you expect (e.g., via opencode.json)
  - You can temporarily log sys.executable in mcp_servers/generic_server.py to confirm
- Confirm .env is loaded
  - .env at the repo root is loaded once at server startup; restart the server after edits
  - Environment keys required by your tools should be present in .env
- Check tool discovery
  - List tools via OpenCode: "Call personal/list_loaded_tools and return only the JSON."
  - If a tool name is missing, verify the module under tools/ exports it via one of the supported patterns
- Diagnose import errors
  - If a tool depends on an external package, ensure it’s available in the server runtime
  - Options: use uvx with --with PACKAGE_NAME in opencode.json or point to a Python where the package is installed
- Reload without restarting
  - Use personal/reload_tools to rescan tools/ after adding/removing modules
- Keep servers thin
  - Avoid per-tool environment loading; rely on the server’s single .env load at startup
