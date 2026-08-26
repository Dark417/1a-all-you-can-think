"""MCP server #2: the ticket tracker.

The second, independent MCP process — so the harness demonstrably routes
calls to the right server, not just 'an' MCP server. Holds sprint tickets
and accepts status updates (a stateful MCP server: mutations persist for the
lifetime of the connection).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from harness.mcp.protocol import StdioServer  # noqa: E402

TICKETS = [
    {"key": "DEMO-41", "status": "todo",
     "title": "Add stdev() to stats.py",
     "notes": "Sample stdev (n-1). Must raise ValueError on fewer than 2 values."},
    {"key": "DEMO-42", "status": "todo",
     "title": "median() crashes on empty list",
     "notes": "Reported by QA; see github issue #1."},
    {"key": "DEMO-38", "status": "done",
     "title": "Add mean() and median()",
     "notes": "Shipped last sprint."},
]


class TicketServer(StdioServer):
    name = "tickets"

    def tools(self):
        return [
            {
                "name": "list_tickets",
                "description": "List sprint tickets, optionally filtered by status (todo|doing|done).",
                "inputSchema": {"type": "object",
                                "properties": {"status": {"type": "string"}},
                                "required": []},
            },
            {
                "name": "update_ticket",
                "description": "Set a ticket's status by key (e.g. DEMO-41 -> doing / done).",
                "inputSchema": {"type": "object",
                                "properties": {"key": {"type": "string"}, "status": {"type": "string"}},
                                "required": ["key", "status"]},
            },
        ]

    def call_tool(self, tool_name, arguments):
        if tool_name == "list_tickets":
            status = arguments.get("status")
            rows = [t for t in TICKETS if not status or t["status"] == status]
            return json.dumps(rows, indent=2)
        if tool_name == "update_ticket":
            key, status = arguments.get("key"), arguments.get("status")
            if status not in ("todo", "doing", "done"):
                raise ValueError("status must be todo | doing | done")
            for ticket in TICKETS:
                if ticket["key"] == key:
                    ticket["status"] = status
                    return f"{key} -> {status}"
            raise ValueError(f"no ticket {key!r}")
        raise ValueError(f"unknown tool {tool_name!r}")


if __name__ == "__main__":
    TicketServer().serve_forever()
