"""Context engineering: the deliberate assembly of what the model sees.

A model call is stateless. Everything the agent "knows" on a given turn is
whatever this module chooses to put in the request — nothing more. That makes
context a budget to be spent, and this file is the ledger.

The assembly order is fixed and deliberate (stable prefix first, volatile
content last, which is also what makes prompt caching work):

    1. identity        - who this agent is (role prompt)
    2. environment     - cwd, platform, date
    3. project memory  - AGENT.md, the persistent per-project instructions
    4. task brief      - what the parent/user asked THIS agent to do
    5. history         - the conversation so far (turns + tool results),
                         possibly with older turns replaced by a compaction
                         summary block

Each agent owns exactly one ContextWindow. Sub-agents do NOT share or inherit
their parent's window — isolation is the point of spawning one (see
orchestrator.py). The only things that cross the boundary are the task brief
going down and a summary coming back.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .providers import estimate_tokens, estimate_tokens_blocks


@dataclass
class Turn:
    """One entry of conversation history: a user/assistant message or a
    tool-result batch. Kept with its token estimate so budget math is O(1)."""
    role: str                       # "user" | "assistant"
    content: Any                    # str or list of content blocks
    tokens: int = 0
    kind: str = "message"           # "message" | "tool_result" | "compaction_summary"

    def to_message(self) -> dict[str, Any]:
        return {"role": self.role, "content": self.content}


@dataclass
class ContextWindow:
    """One agent's working memory, with explicit accounting."""

    agent_id: str
    max_tokens: int                       # the budget this agent must live within
    identity: str = ""                    # section 1
    environment: str = ""                 # section 2
    project_memory: str = ""              # section 3
    task_brief: str = ""                  # section 4
    turns: list[Turn] = field(default_factory=list)   # section 5
    compactions: int = 0

    # ---- writing ----------------------------------------------------------

    def add_user(self, content: Any) -> None:
        self._add("user", content, "message")

    def add_assistant(self, content: Any) -> None:
        self._add("assistant", content, "message")

    def add_tool_results(self, results: list[dict[str, Any]]) -> None:
        # tool results ride in a user message, per the Messages API
        self._add("user", results, "tool_result")

    def _add(self, role: str, content: Any, kind: str) -> None:
        tokens = estimate_tokens(content) if isinstance(content, str) else estimate_tokens_blocks(content)
        self.turns.append(Turn(role=role, content=content, tokens=tokens, kind=kind))

    # ---- assembly ---------------------------------------------------------

    def system_prompt(self) -> str:
        sections = [
            self.identity,
            f"# Environment\n{self.environment}" if self.environment else "",
            f"# Project memory (AGENT.md)\n{self.project_memory}" if self.project_memory else "",
            f"# Your task\n{self.task_brief}" if self.task_brief else "",
        ]
        return "\n\n".join(s for s in sections if s)

    def messages(self) -> list[dict[str, Any]]:
        return [t.to_message() for t in self.turns]

    # ---- accounting -------------------------------------------------------

    def fixed_tokens(self) -> int:
        return estimate_tokens(self.system_prompt())

    def history_tokens(self) -> int:
        return sum(t.tokens for t in self.turns)

    def used_tokens(self) -> int:
        return self.fixed_tokens() + self.history_tokens()

    def utilization(self) -> float:
        return self.used_tokens() / self.max_tokens if self.max_tokens else 0.0

    def snapshot(self) -> dict[str, Any]:
        """What the UI renders as the per-agent context gauge."""
        return {
            "agent_id": self.agent_id,
            "max_tokens": self.max_tokens,
            "fixed_tokens": self.fixed_tokens(),
            "history_tokens": self.history_tokens(),
            "used_tokens": self.used_tokens(),
            "utilization": round(self.utilization(), 3),
            "turns": len(self.turns),
            "compactions": self.compactions,
        }
