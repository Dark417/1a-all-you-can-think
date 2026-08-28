"""The LangGraph agent.

    START -> agent -> (tool calls?) -> tools -> agent -> ... -> END

`agent` is one model call; `tools` executes whatever tool calls it emitted.
State is the message list; a MemorySaver checkpointer persists it per
`thread_id`, so multi-turn memory is "same thread_id" — nothing else.

The model is `langchain_openai.ChatOpenAI` pointed at BazaarLink's
OpenAI-compatible base_url; swap MODEL in .env to try any model it serves.
"""

from __future__ import annotations

import os

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph  # noqa: F401 (END used by tools_condition)
from langgraph.prebuilt import ToolNode, tools_condition

from tools import TOOLS

SYSTEM_PROMPT = (
    "You are a concise, friendly assistant. Use the calculator tool for any "
    "arithmetic and the current_time tool when asked about the date or time; "
    "otherwise answer from your own knowledge and say so when unsure."
)


def make_llm(model: str | None = None) -> ChatOpenAI:
    return ChatOpenAI(
        model=model or os.getenv("MODEL", "qwen/qwen3.7-flash:free"),
        api_key=os.environ["OPENAI_API_KEY"],
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.bazaarlink.ai/v1"),
        temperature=0.3,
        streaming=True,
    )


def build_graph(model: str | None = None):
    llm = make_llm(model).bind_tools(TOOLS)

    async def agent(state: MessagesState) -> dict:
        msgs = [SystemMessage(SYSTEM_PROMPT), *state["messages"]]
        return {"messages": [await llm.ainvoke(msgs)]}

    g = StateGraph(MessagesState)
    g.add_node("agent", agent)
    g.add_node("tools", ToolNode(TOOLS))
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", tools_condition)   # routes to "tools" or END
    g.add_edge("tools", "agent")
    return g.compile(checkpointer=MemorySaver())
