"""The agent loop. This is the whole trick.

    while the model asks for tools:
        assemble context -> call model -> execute tool calls ->
        feed results back -> maybe compact -> repeat

Everything else in the harness exists to feed this loop (context.py,
memory.py), extend it (tools/, mcp/), multiply it (orchestrator.py) or
observe it (events.py, session.py). The loop itself stays ~60 lines.
"""

from __future__ import annotations

from dataclasses import dataclass

from .compaction import Compactor
from .context import ContextWindow
from .events import EventBus
from .providers import ModelProvider, ModelRequest
from .tools import ToolRegistry

MAX_TURNS = 20


@dataclass
class AgentResult:
    agent_id: str
    text: str
    turns: int
    stop: str            # "completed" | "max_turns"


class Agent:
    def __init__(self, agent_id: str, role: str, window: ContextWindow,
                 registry: ToolRegistry, provider: ModelProvider,
                 compactor: Compactor, bus: EventBus) -> None:
        self.id = agent_id
        self.role = role
        self.window = window
        self.registry = registry
        self.provider = provider
        self.compactor = compactor
        self.bus = bus

    def run(self, user_message: str) -> AgentResult:
        self.window.add_user(user_message)

        for turn in range(1, MAX_TURNS + 1):
            request = ModelRequest(
                system=self.window.system_prompt(),
                messages=self.window.messages(),
                tools=self.registry.schemas(),
                agent_role=self.role,
            )
            response = self.provider.complete(request)

            self.bus.emit(
                "agent.turn", agent_id=self.id, turn=turn,
                stop_reason=response.stop_reason,
                input_tokens=response.input_tokens, output_tokens=response.output_tokens,
                text=response.text[:500],
                tool_calls=[b["name"] for b in response.tool_uses],
                context=self.window.snapshot(),
            )

            self.window.add_assistant(response.content)

            if response.stop_reason != "tool_use":
                return AgentResult(self.id, response.text, turn, "completed")

            # Execute every tool_use from this turn; all results ride back in
            # ONE user message (splitting them teaches the model not to
            # parallelize).
            results = [self.registry.dispatch(self.id, block) for block in response.tool_uses]
            self.window.add_tool_results(results)

            # Compaction check happens after results land — tool output is what
            # actually fills the window.
            self.compactor.maybe_compact(self.window)

        return AgentResult(self.id, "(agent hit its turn budget before finishing)", MAX_TURNS, "max_turns")
