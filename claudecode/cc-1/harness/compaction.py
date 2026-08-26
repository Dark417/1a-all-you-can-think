"""Context compaction: what to do when the window is nearly full.

The strategy mirrors what real harnesses (Claude Code included) do:

  1. Watch utilization after every turn.
  2. When it crosses a threshold (default 75%), take the OLDER portion of the
     history — everything except the last few turns, which the agent still
     actively needs — and ask the model to compress it into a structured
     summary: decisions made, files touched, results learned, open questions.
  3. Replace those turns with a single synthetic user turn labelled as a
     compaction summary. The recent turns are kept verbatim.

What is deliberately lost: the raw bytes of old tool results (a 2,000-line
file read that mattered for one decision). What is deliberately kept: the
decision itself. That trade — provenance for headroom — is the essence of
compaction, and why harnesses also write important facts to durable memory
(memory.py) *before* they get compacted away.
"""

from __future__ import annotations

import json

from .context import ContextWindow, Turn
from .events import EventBus
from .providers import ModelProvider, estimate_tokens

DEFAULT_THRESHOLD = 0.75   # compact when the window is 75% full
KEEP_RECENT_TURNS = 4      # never summarize away the freshest context


class Compactor:
    def __init__(self, provider: ModelProvider, bus: EventBus,
                 threshold: float = DEFAULT_THRESHOLD, keep_recent: int = KEEP_RECENT_TURNS) -> None:
        self.provider = provider
        self.bus = bus
        self.threshold = threshold
        self.keep_recent = keep_recent

    def maybe_compact(self, window: ContextWindow) -> bool:
        if window.utilization() < self.threshold:
            return False
        # Need enough old turns for compaction to actually buy headroom
        if len(window.turns) <= self.keep_recent + 1:
            return False

        old = window.turns[: -self.keep_recent]
        recent = window.turns[-self.keep_recent:]
        before_tokens = window.used_tokens()

        transcript = _render(old)
        summary = self.provider.summarize(
            transcript,
            "Compress this agent transcript into a compact briefing titled "
            "'Summary of earlier work'. Preserve: decisions and their reasons, "
            "files read or changed (with paths), key results and numbers, and "
            "unresolved questions. Omit raw file contents and tool chatter.",
        )

        summary_turn = Turn(
            role="user",
            content=(
                "[CONTEXT COMPACTED] Earlier conversation was summarized to free "
                f"context space ({len(old)} turns compressed):\n\n{summary}"
            ),
            tokens=estimate_tokens(summary) + 30,
            kind="compaction_summary",
        )

        # History must still start with a user turn for the Messages API.
        window.turns = [summary_turn] + list(recent)
        if window.turns and window.turns[0].role != "user":
            window.turns.insert(0, summary_turn)  # defensive; summary_turn is user-role
        window.compactions += 1

        self.bus.emit(
            "compaction",
            agent_id=window.agent_id,
            turns_compacted=len(old),
            tokens_before=before_tokens,
            tokens_after=window.used_tokens(),
            summary_preview=summary[:400],
        )
        return True


def _render(turns: list[Turn]) -> str:
    """Flatten turns to text for the summarizer."""
    lines: list[str] = []
    for turn in turns:
        if isinstance(turn.content, str):
            lines.append(f"{turn.role.upper()}: {turn.content}")
            continue
        for block in turn.content:
            btype = block.get("type")
            if btype == "text":
                lines.append(f"{turn.role.upper()}: {block.get('text', '')}")
            elif btype == "tool_use":
                lines.append(f"{turn.role.upper()} called tool {block.get('name')} "
                             f"with {json.dumps(block.get('input', {}))[:300]}")
            elif btype == "tool_result":
                content = block.get("content", "")
                if isinstance(content, list):
                    content = " ".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
                lines.append(f"TOOL RESULT: {str(content)[:500]}")
    return "\n".join(lines)
