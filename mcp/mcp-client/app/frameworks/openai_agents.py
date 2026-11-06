"""OpenAI Agents SDK: two ways to use MCP.

1. ask():                client-side. MCPServerStreamableHttp is an async context manager
                         passed as Agent(mcp_servers=[...]); the SDK lists tools every run.
2. ask_via_hosted_mcp(): HostedMCPTool. The Responses API calls the server from OpenAI's
                         cloud, so it must be publicly reachable (PUBLIC_MCP_SERVER_URL).
Auth: OPENAI_API_KEY.
"""

from agents import Agent, HostedMCPTool, Runner
from agents.mcp import MCPServerStreamableHttp

from app.config import settings


def _agent(**kwargs) -> Agent:
    if settings.openai_model:
        kwargs["model"] = settings.openai_model
    return Agent(name="mcp-demo", instructions=settings.system_prompt, **kwargs)


async def ask(prompt: str) -> str:
    # MCP-specific: MCP servers are a first-class Agent field, separate from tools=[...].
    async with MCPServerStreamableHttp(
        name="demo", params={"url": settings.mcp_server_url}, cache_tools_list=True
    ) as server:
        result = await Runner.run(_agent(mcp_servers=[server]), prompt)
    return str(result.final_output)


async def ask_via_hosted_mcp(prompt: str) -> str:
    if not settings.public_mcp_server_url:
        raise RuntimeError("Set PUBLIC_MCP_SERVER_URL: OpenAI's cloud cannot reach localhost.")
    tool = HostedMCPTool(
        tool_config={
            "type": "mcp",
            "server_label": "demo",
            "server_url": settings.public_mcp_server_url,
            "require_approval": "never",
        }
    )
    result = await Runner.run(_agent(tools=[tool]), prompt)
    return str(result.final_output)
