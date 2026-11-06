"""LangGraph: MCP tools become LangChain tools; you own the graph.

The MCP-specific part is two lines (MultiServerMCPClient + get_tools). The rest is plain
LangGraph: a model node, a ToolNode, and a conditional edge looping between them.
"""

from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.config import settings


async def ask(prompt: str) -> str:
    # MCP-specific: a dict of named servers -> LangChain BaseTool objects.
    # Each tool call opens its own short MCP session (stateless by default).
    client = MultiServerMCPClient(
        {"demo": {"transport": "streamable_http", "url": settings.mcp_server_url}}
    )
    tools = await client.get_tools()

    # LangGraph is model-agnostic; any init_chat_model provider works here.
    model = init_chat_model(f"anthropic:{settings.anthropic_model}").bind_tools(tools)

    async def call_model(state: MessagesState) -> dict:
        return {"messages": [await model.ainvoke(state["messages"])]}

    graph = StateGraph(MessagesState)
    graph.add_node("model", call_model)
    graph.add_node("tools", ToolNode(tools))
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", tools_condition)  # tool calls -> "tools", else END
    graph.add_edge("tools", "model")
    app = graph.compile()

    result = await app.ainvoke(
        {"messages": [("system", settings.system_prompt), ("user", prompt)]}
    )
    return result["messages"][-1].text
