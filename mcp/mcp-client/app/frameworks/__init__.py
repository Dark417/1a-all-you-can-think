"""Registry: one entry per framework. Modules import lazily, so one broken SDK can't break the rest.

Every adapter exposes the same shape:  async def <func>(prompt: str) -> str
"""

import importlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Framework:
    name: str
    module: str
    func: str
    mcp_side: str  # "client": our process speaks MCP; "provider": the vendor's cloud speaks MCP
    how: str


FRAMEWORKS: dict[str, Framework] = {
    f.name: f
    for f in [
        Framework("langgraph", "app.frameworks.langgraph_agent", "ask", "client",
                  "langchain-mcp-adapters turns MCP tools into LangChain tools; you wire the graph"),
        Framework("adk", "app.frameworks.adk_agent", "ask", "client",
                  "McpToolset is just another entry in LlmAgent(tools=[...]); Runner drives it"),
        Framework("vertex", "app.frameworks.vertex_genai", "ask", "client",
                  "No agent framework: pass an MCP ClientSession straight into Gemini's tools"),
        Framework("strands", "app.frameworks.strands_agent", "ask", "client",
                  "MCPClient is a ToolProvider; Agent(tools=[mcp_client]) manages its lifecycle"),
        Framework("agentcore", "app.frameworks.agentcore_app", "ask_via_runtime", "client",
                  "Hosting, not a framework: the Strands agent wrapped in BedrockAgentCoreApp"),
        Framework("claude-api", "app.frameworks.claude_api", "ask", "client",
                  "Anthropic SDK tool runner + async_mcp_tool converts each MCP tool"),
        Framework("claude-connector", "app.frameworks.claude_api", "ask_via_connector", "provider",
                  "Messages API mcp_servers + mcp_toolset: Anthropic's cloud calls the server"),
        Framework("claude-agent-sdk", "app.frameworks.claude_agent_sdk", "ask", "client",
                  "Claude Code as a library: mcp_servers config dict, tools named mcp__server__tool"),
        Framework("openai-agents", "app.frameworks.openai_agents", "ask", "client",
                  "MCPServerStreamableHttp passed as Agent(mcp_servers=[...])"),
        Framework("openai-hosted", "app.frameworks.openai_agents", "ask_via_hosted_mcp", "provider",
                  "HostedMCPTool: the Responses API calls the server from OpenAI's cloud"),
    ]
}


async def ask(name: str, prompt: str) -> str:
    fw = FRAMEWORKS[name]
    module = importlib.import_module(fw.module)
    return await getattr(module, fw.func)(prompt)
