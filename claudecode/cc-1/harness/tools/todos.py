"""The plan/todo tool.

Planning in an agent harness is not a separate 'mode' of the model — it is a
tool the model writes to and the harness renders. Writing the plan into a
tool result puts it *into context*, where it keeps steering later turns; the
UI renders the same structure as a checklist. This is exactly what Claude
Code's TodoWrite does.
"""

from __future__ import annotations

import json
from typing import Any

from . import Tool
from ..events import EventBus

VALID_STATUS = {"pending", "in_progress", "completed"}


class TodoList:
    def __init__(self, bus: EventBus, agent_id: str) -> None:
        self.bus = bus
        self.agent_id = agent_id
        self.items: list[dict[str, Any]] = []

    def write(self, todos_json: str) -> str:
        try:
            items = json.loads(todos_json)
            assert isinstance(items, list)
        except (json.JSONDecodeError, AssertionError):
            return 'ERROR: todos must be a JSON array like [{"task": "...", "status": "pending"}]'
        cleaned = []
        for item in items:
            task = str(item.get("task", "")).strip()
            status = item.get("status", "pending")
            if not task or status not in VALID_STATUS:
                return f"ERROR: each todo needs a task and a status in {sorted(VALID_STATUS)}"
            cleaned.append({"task": task, "status": status})
        self.items = cleaned
        self.bus.emit("plan.updated", agent_id=self.agent_id, todos=cleaned)
        done = sum(1 for t in cleaned if t["status"] == "completed")
        return f"Plan recorded: {len(cleaned)} steps, {done} completed.\n" + "\n".join(
            f"  [{'x' if t['status'] == 'completed' else '>' if t['status'] == 'in_progress' else ' '}] {t['task']}"
            for t in cleaned
        )


def make_todo_tool(bus: EventBus, agent_id: str) -> tuple[Tool, TodoList]:
    todo_list = TodoList(bus, agent_id)
    tool = Tool(
        "write_plan",
        "Record or update your step-by-step plan as a JSON array of "
        '{"task": string, "status": "pending"|"in_progress"|"completed"}. '
        "Re-call this as steps complete so progress is visible.",
        {"type": "object", "properties": {"todos_json": {"type": "string"}}, "required": ["todos_json"]},
        todo_list.write,
        capability="read",
    )
    return tool, todo_list
