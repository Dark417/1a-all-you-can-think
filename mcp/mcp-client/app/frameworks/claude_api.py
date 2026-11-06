"""Claude API (Anthropic Python SDK): two ways to use MCP.

1. ask():               client-side. Your process holds the MCP session; async_mcp_tool
                        converts each MCP tool and the SDK's tool runner drives the loop.
2. ask_via_connector(): server-side MCP connector. Anthropic's cloud connects to the server,
                        so it must be publicly reachable (PUBLIC_MCP_SERVER_URL).

Both enable server-side refusal fallbacks (fallbacks="default"), routed by refusal category.
"""

from anthropic import AsyncAnthropic
from anthropic.lib.tools.mcp import async_mcp_tool

from app.config import settings
from app.frameworks.raw_mcp import open_session

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _text(message) -> str:
    return "".join(b.text for b in message.content if b.type == "text")


async def ask(prompt: str) -> str:
    client = AsyncAnthropic()
    async with open_session() as session:
        mcp_tools = (await session.list_tools()).tools
        # MCP-specific: one call converts each MCP tool to a runnable SDK tool bound to the session.
        runner = client.beta.messages.tool_runner(
            model=settings.anthropic_model,
            max_tokens=16000,
            system=settings.system_prompt,
            messages=[{"role": "user", "content": prompt}],
            tools=[async_mcp_tool(t, session) for t in mcp_tools],
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        final = await runner.until_done()
    return _text(final)


async def ask_via_connector(prompt: str) -> str:
    if not settings.public_mcp_server_url:
        raise RuntimeError("Set PUBLIC_MCP_SERVER_URL: Anthropic's cloud cannot reach localhost.")
    client = AsyncAnthropic()
    # MCP-specific: declare the server AND a matching mcp_toolset; no client-side loop at all.
    message = await client.beta.messages.create(
        model=settings.anthropic_model,
        max_tokens=16000,
        system=settings.system_prompt,
        messages=[{"role": "user", "content": prompt}],
        mcp_servers=[{"type": "url", "url": settings.public_mcp_server_url, "name": "demo"}],
        tools=[{"type": "mcp_toolset", "mcp_server_name": "demo"}],
        betas=["mcp-client-2025-11-20", FALLBACK_BETA],
        fallbacks="default",
    )
    return _text(message)
