"""Claude Agent SDK: Claude Code packaged as a library.

MCP servers are a config dict (same shape as .mcp.json); tools appear to the model as
mcp__<server>__<tool> and must be allowed like any other Claude Code tool.
Auth: ANTHROPIC_API_KEY (or an existing Claude Code login).
"""

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from app.config import settings


async def ask(prompt: str) -> str:
    options = ClaudeAgentOptions(
        model=settings.anthropic_model,
        system_prompt=settings.system_prompt,
        # MCP-specific: declarative config; the SDK's Claude Code process owns the connection.
        mcp_servers={"demo": {"type": "http", "url": settings.mcp_server_url}},
        allowed_tools=["mcp__demo"],  # pre-approve every tool on the "demo" server
        tools=[],  # no built-in Read/Bash/etc.; only MCP tools
        setting_sources=[],  # ignore user/project settings for a reproducible demo
        max_turns=6,
    )
    answer = ""
    async for message in query(prompt=prompt, options=options):
        if isinstance(message, ResultMessage):
            answer = message.result or ""
    return answer
