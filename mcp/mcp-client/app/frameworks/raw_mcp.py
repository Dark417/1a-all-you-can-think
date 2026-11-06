"""Baseline: the official MCP Python SDK with no LLM and no framework.

Every framework below does this same handshake underneath:
open transport -> initialize -> list_tools -> call_tool.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from app.config import settings


@asynccontextmanager
async def open_session(url: str | None = None) -> AsyncIterator[ClientSession]:
    async with streamable_http_client(url or settings.mcp_server_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def inspect_server() -> dict:
    async with open_session() as s:
        tools = (await s.list_tools()).tools
        resources = (await s.list_resources()).resources
        prompts = (await s.list_prompts()).prompts
    return {
        "url": settings.mcp_server_url,
        "tools": [{"name": t.name, "description": t.description, "input_schema": t.inputSchema,
                   "output_schema": t.outputSchema} for t in tools],
        "resources": [{"uri": str(r.uri), "name": r.name, "mime_type": r.mimeType} for r in resources],
        "prompts": [{"name": p.name, "arguments": [a.name for a in p.arguments or []]} for p in prompts],
    }


async def call_tool(tool: str, arguments: dict) -> dict:
    async with open_session() as s:
        result = await s.call_tool(tool, arguments)
    return {
        "is_error": result.isError,
        "text": [c.text for c in result.content if c.type == "text"],
        "structured": result.structuredContent,
    }
