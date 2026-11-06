# MCP Server

> Two MCP servers, one Python FastAPI and one Java Spring Boot, implementing one identical contract.

## Index

- [1. Projects](#1-projects)
- [2. Shared Contract](#2-shared-contract)
- [3. How They Differ](#3-how-they-differ)
- [4. Observed Wire Differences](#4-observed-wire-differences)
- [Where This Fits](#where-this-fits)
- [References](#references)

## 1. Projects

Both servers expose MCP over Streamable HTTP at `/mcp` and mirror the same functions as REST.

| Project | Stack | Port | Run |
| --- | --- | --- | --- |
| [fastapi-mcp-server/](fastapi-mcp-server/) | Python 3.12, FastAPI, `mcp` 2.3 | 8001 | `uv run uvicorn app.main:app --port 8001` |
| [springboot-mcp-server/](springboot-mcp-server/) | Java 17+, Spring Boot 4.1, Spring AI 2.0 | 8002 | `mvn spring-boot:run` |

## 2. Shared Contract

Names, arguments, and JSON keys match exactly, so any client works with either server.

| Kind | Name | Input | Output |
| --- | --- | --- | --- |
| Tool | `add` | `a`, `b` integers | sum |
| Tool | `get_weather` | `city` string | `{city, condition, temp_c}` (fake) |
| Tool | `search_notes` | `query` string | matching notes |
| Resource | `notes://all` | none | all notes, `text/plain` |
| Prompt | `summarize_notes` | `topic` string | instruction text |

The REST mirror is `GET /health`, `/api/add`, `/api/weather/{city}`, and `/api/notes`.

## 3. How They Differ

The protocol is identical; how you declare and wire the server is not.

| Aspect | FastAPI (Python) | Spring Boot (Java) |
| --- | --- | --- |
| Declare a tool | `@mcp.tool()` on a function | `@McpTool` on a bean method |
| Tool description | Docstring | `description =` attribute |
| Input schema | Type hints | Parameter types + `@McpToolParam` |
| Output schema | Automatic from return type | Opt-in `generateOutputSchema = true` |
| Wiring | Mount ASGI app; start session manager | Starter auto-configures from `application.yml` |
| Stateless mode | `stateless_http=True` | `protocol: stateless` |

- Python is explicit code: you mount the MCP app and run its lifespan yourself.
- Spring is convention: add the starter, annotate beans, and a scanner registers them at startup.

## 4. Observed Wire Differences

The same client call returned these differences on 2026-11-03.

| Call | FastAPI result | Spring Boot result |
| --- | --- | --- |
| `add(2, 3)` | Text `5` + structured `{"result": 5}` | Text `5` only |
| `search_notes` | Structured `{"result": [...]}` | JSON text only |
| `get_weather` | All three fields required | `temp_c` optional in schema |
| Param descriptions | Absent unless added | Present from `@McpToolParam` |
| Protocol version | `2025-11-25` | `2025-11-25` |

Python wraps primitives and lists in `{"result": ...}` for `structuredContent`; Spring returns text unless asked.

## Where This Fits

This folder is the server half of a learning pair; [../mcp-client/](../mcp-client/) is the client half.

- After reading it, you can build an MCP server in either stack.
- Point the client at `8001` or `8002` to see that clients cannot tell them apart.

## References

- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [MCP Java SDK](https://github.com/modelcontextprotocol/java-sdk)
- [Spring AI MCP](https://docs.spring.io/spring-ai/reference/api/mcp/mcp-overview.html)
