"""RAG-as-a-tool: the agent decides when and what to retrieve."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..vectorstore import VectorStore
    from . import Tool


def build_search_tool(store: "VectorStore") -> "Tool":
    from . import Tool

    def handler(payload: dict[str, Any]) -> dict[str, Any]:
        query = (payload.get("query") or "").strip()
        k = int(payload.get("k", 5))
        k = max(1, min(k, 10))
        if not query:
            return {"error": "query is required"}
        hits = store.query(query, k=k)
        if not hits:
            return {"hits": [], "note": "knowledge base is empty or no matches"}
        return {
            "hits": [
                {
                    "rank": i + 1,
                    "source": h.source,
                    "section": h.section,
                    "score": round(h.score, 4),
                    "text": h.text,
                }
                for i, h in enumerate(hits)
            ]
        }

    return Tool(
        name="search_knowledge_base",
        description=(
            "Search the user's local tutorial corpus on AI-agent architecture. "
            "Returns the top-k passages with source filename and section. "
            "Call this BEFORE answering any non-trivial conceptual question."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Natural-language query. Rephrase the user's "
                    "question into search-friendly terms.",
                },
                "k": {
                    "type": "integer",
                    "description": "How many passages to return (1-10).",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
        },
        handler=handler,
    )
