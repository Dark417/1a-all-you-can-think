"""AWS Strands Agents: MCPClient is a ToolProvider the Agent manages for you.

You pass a *factory* for the transport; Strands runs the MCP session on a background
thread and starts/stops it with the agent. Auth: the standard AWS credential chain.
"""

from mcp.client.streamable_http import streamable_http_client
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient

from app.config import settings


def build_agent() -> Agent:
    # MCP-specific: a zero-arg callable returning the transport context manager.
    mcp_client = MCPClient(lambda: streamable_http_client(settings.mcp_server_url))
    model_kwargs = {"region_name": settings.aws_region}
    if settings.bedrock_model_id:
        model_kwargs["model_id"] = settings.bedrock_model_id
    return Agent(
        model=BedrockModel(**model_kwargs),
        system_prompt=settings.system_prompt,
        tools=[mcp_client],  # ToolProvider: started lazily, stopped by agent.cleanup()
        callback_handler=None,  # no streaming to stdout
    )


async def ask(prompt: str) -> str:
    agent = build_agent()
    try:
        result = await agent.invoke_async(prompt)
    finally:
        agent.cleanup()
    return str(result).strip()
