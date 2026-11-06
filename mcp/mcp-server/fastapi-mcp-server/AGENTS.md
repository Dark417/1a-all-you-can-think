# Agent Rules: fastapi-mcp-server

> Rules every agent follows when working in this project.

## 1. Stack And Commands

This is a Python 3.12 FastAPI app managed with `uv`, using `mcp` 2.x.

- **Install**: `uv sync`
- **Test**: `uv run pytest -q`
- **Run**: `uv run uvicorn app.main:app --port 8001`

## 2. Conventions

The contract is shared with `../springboot-mcp-server`, so changes go to both.

- Keep business logic in `app/domain.py`, free of MCP and FastAPI imports.
- Expose each function through both `app/mcp_server.py` and a REST route.
- Keep tool names, argument names, and JSON keys identical to the Spring server.
- Update `../README.md` tables when the contract or a difference changes.

## 3. Limits

- Use `mcp.server.mcpserver.MCPServer`; `mcp.server.fastmcp` no longer exists in 2.x.
- Keep port 8001; the client defaults to it.
