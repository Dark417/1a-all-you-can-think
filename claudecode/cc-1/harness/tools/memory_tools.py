"""Memory as tools: the model decides what to remember, explicitly."""

from __future__ import annotations

from . import Tool
from ..memory import MemoryStore


def make_memory_tools(store: MemoryStore, agent_id: str) -> list[Tool]:
    def note(topic: str, content: str) -> str:
        return store.add_note(agent_id, topic, content)

    def learn(lesson: str) -> str:
        return store.append_project_memory(lesson)

    return [
        Tool("memory_note",
             "Save a fact to this session's notes so it survives context compaction "
             "and is visible to other agents in the session. Use for findings, decisions, gotchas.",
             {"type": "object", "properties": {
                 "topic": {"type": "string"}, "content": {"type": "string"}},
              "required": ["topic", "content"]},
             note, capability="read"),
        Tool("memory_learn",
             "Append a durable lesson to the project's AGENT.md. It will be loaded into "
             "every future session. Use sparingly, for things that are true beyond this task.",
             {"type": "object", "properties": {"lesson": {"type": "string"}}, "required": ["lesson"]},
             learn, capability="write"),
    ]
