"""MCP server #1: internal docs / knowledge base.

Runs as its own process, speaks newline-delimited JSON-RPC on stdio, and
knows things the workspace files do not — which is what makes the researcher
sub-agent actually need it. Run it by hand to poke at the protocol:

    echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python3 docs_server.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # make `harness` importable

from harness.mcp.protocol import StdioServer  # noqa: E402

DOCS = {
    "style-guide": (
        "Team style guide: pure functions, type hints everywhere, docstrings in "
        "imperative mood. Errors: raise ValueError with actionable messages — never "
        "return None to signal failure. Tests live next to code as test_<module>.py "
        "and run with plain pytest."
    ),
    "stats-module": (
        "stats.py design notes: it is the numeric core of the demo project. Public "
        "API is mean(), median(), and (planned) stdev(). All functions take a "
        "sequence of numbers and must reject empty input with ValueError. stdev() "
        "should be the SAMPLE standard deviation (n-1 denominator) per the 2024 "
        "design review."
    ),
    "release-process": (
        "Release process: every change needs a green pytest run and a PR with a "
        "one-paragraph summary. Direct pushes to main are blocked."
    ),
}


class DocsServer(StdioServer):
    name = "docs"

    def tools(self):
        return [
            {
                "name": "search_docs",
                "description": "Search the team knowledge base by keyword; returns matching doc ids and snippets.",
                "inputSchema": {"type": "object",
                                "properties": {"query": {"type": "string"}},
                                "required": ["query"]},
            },
            {
                "name": "read_doc",
                "description": "Read one knowledge-base document in full by id.",
                "inputSchema": {"type": "object",
                                "properties": {"doc_id": {"type": "string"}},
                                "required": ["doc_id"]},
            },
        ]

    def call_tool(self, tool_name, arguments):
        if tool_name == "search_docs":
            query = arguments.get("query", "").lower()
            hits = [
                f"[{doc_id}] {text[:120]}…"
                for doc_id, text in DOCS.items()
                if any(word in text.lower() or word in doc_id for word in query.split())
            ]
            return "\n".join(hits) if hits else f"No docs match {query!r}. Available: {', '.join(DOCS)}"
        if tool_name == "read_doc":
            doc_id = arguments.get("doc_id", "")
            if doc_id in DOCS:
                return f"# {doc_id}\n{DOCS[doc_id]}"
            raise ValueError(f"no doc {doc_id!r}; available: {', '.join(DOCS)}")
        raise ValueError(f"unknown tool {tool_name!r}")


if __name__ == "__main__":
    DocsServer().serve_forever()
