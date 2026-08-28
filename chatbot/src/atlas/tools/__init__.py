"""Tool registry. Each tool is a small object exposing:

- `spec()`     -> Anthropic-format tool schema for the model.
- `run(input)` -> JSON-serializable result the model will see as a
                  tool_result block."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..memory import NoteStore
from ..vectorstore import VectorStore
from .clock import build_clock_tool
from .notes import build_note_tools
from .search_kb import build_search_tool


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[dict[str, Any]], Any]

    def spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def run(self, payload: dict[str, Any]) -> Any:
        return self.handler(payload or {})


class ToolRegistry:
    def __init__(self, tools: list[Tool]) -> None:
        self._by_name = {t.name: t for t in tools}

    def specs(self) -> list[dict[str, Any]]:
        return [t.spec() for t in self._by_name.values()]

    def names(self) -> list[str]:
        return list(self._by_name.keys())

    def run(self, name: str, payload: dict[str, Any]) -> Any:
        if name not in self._by_name:
            return {"error": f"unknown tool: {name}"}
        return self._by_name[name].run(payload)


def default_registry(
    vector_store: VectorStore | None = None,
    note_store: NoteStore | None = None,
) -> ToolRegistry:
    vector_store = vector_store or VectorStore()
    note_store = note_store or NoteStore()
    tools: list[Tool] = [
        build_search_tool(vector_store),
        *build_note_tools(note_store),
        build_clock_tool(),
    ]
    return ToolRegistry(tools)
