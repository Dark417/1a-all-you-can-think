# FastAPI MCP Server

> An MCP server built with the official Python SDK, mounted inside a FastAPI app.

## Index

- [1. Run](#1-run)
- [2. Layout](#2-layout)
- [3. How It Works](#3-how-it-works)

## 1. Run

Requires `uv`; it installs Python 3.12 if needed.

```bash
uv sync
uv run uvicorn app.main:app --port 8001     # MCP at http://localhost:8001/mcp
uv run pytest -q                            # real server on a free port + MCP client
```

- REST mirror: `curl localhost:8001/api/weather/Tokyo`.
- The shared contract and the Spring comparison are in [../README.md](../README.md).

## 2. Layout

```text
app/
├── domain.py       plain logic: add, get_weather, search_notes
├── mcp_server.py   MCP surface: @mcp.tool / @mcp.resource / @mcp.prompt
└── main.py         FastAPI: REST routes + mounted /mcp
tests/test_server.py
```

## 3. How It Works

MCP and REST are two front doors onto the same `domain` functions.

- `MCPServer` (renamed from `FastMCP` in `mcp` 2.x) derives schemas from type hints.
- `streamable_http_app(stateless_http=True)` returns an ASGI app serving `/mcp`.
- FastAPI's lifespan runs `mcp.session_manager.run()`; mounted apps never run their own.
- The mount goes last, so FastAPI routes match before the catch-all MCP app.
