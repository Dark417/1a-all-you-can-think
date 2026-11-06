"""MCP surface, built with the official Python SDK (mcp 2.x `MCPServer`, formerly `FastMCP`).

Python style: decorators + type hints. The SDK derives each tool's JSON schema from
the function signature, its output schema from the return type (a Pydantic model here),
and its description from the docstring.
"""

from mcp.server.mcpserver import MCPServer

from app import domain

mcp = MCPServer(name="demo-mcp-fastapi", version="0.1.0")


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers and return the sum."""
    return domain.add(a, b)


@mcp.tool()
def get_weather(city: str) -> domain.Weather:
    """Get the (fake, deterministic) current weather for a city."""
    return domain.get_weather(city)


@mcp.tool()
def search_notes(query: str) -> list[str]:
    """Search the in-memory notes for a case-insensitive substring."""
    return domain.search_notes(query)


@mcp.resource("notes://all", name="all_notes", mime_type="text/plain")
def all_notes() -> str:
    """Every note, one per line."""
    return "\n".join(domain.NOTES)


@mcp.prompt()
def summarize_notes(topic: str) -> str:
    """Ask the model to summarize the notes about a topic."""
    return f"Use the search_notes tool to find notes about '{topic}', then summarize them in 3 bullets."
