"""Memory: what survives when context does not.

Three tiers, from most to least durable — the same shape as real harnesses
(Claude Code's CLAUDE.md, auto-memory, and session transcripts):

  project memory   AGENT.md at the workspace root. Human- and agent-editable
                   standing instructions ("run tests with pytest", "never
                   touch generated/"). Loaded into every agent's system
                   prompt, every session. The agent can append lessons to it
                   via the memory tool.

  session notes    A scratchpad keyed to one session. Agents write facts here
                   *before* compaction can eat them; anything here is
                   re-injectable on resume.

  transcript       The full JSONL event log (session.py). Never loaded into
                   context wholesale — it is the archival record, searched,
                   not replayed.

The important design point: memory writes are an explicit tool the model
calls, not a side effect. The model decides what is worth remembering, the
harness decides where it lives.
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_MEMORY_FILE = "AGENT.md"


class MemoryStore:
    def __init__(self, workspace: Path, session_dir: Path) -> None:
        self.workspace = Path(workspace)
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._notes_file = self.session_dir / "notes.json"

    # ---- project memory (AGENT.md) ---------------------------------------

    def project_memory(self) -> str:
        path = self.workspace / PROJECT_MEMORY_FILE
        return path.read_text() if path.exists() else ""

    def append_project_memory(self, lesson: str) -> str:
        path = self.workspace / PROJECT_MEMORY_FILE
        existing = path.read_text() if path.exists() else f"# {PROJECT_MEMORY_FILE}\n"
        if not existing.endswith("\n"):
            existing += "\n"
        path.write_text(existing + f"- {lesson.strip()}\n")
        return f"Appended to {PROJECT_MEMORY_FILE}."

    # ---- session notes ----------------------------------------------------

    def notes(self) -> list[dict]:
        if self._notes_file.exists():
            return json.loads(self._notes_file.read_text())
        return []

    def add_note(self, agent_id: str, topic: str, content: str) -> str:
        notes = self.notes()
        notes.append({"agent_id": agent_id, "topic": topic, "content": content})
        self._notes_file.write_text(json.dumps(notes, indent=2, ensure_ascii=False))
        return f"Noted under topic {topic!r} ({len(notes)} notes in session)."

    def notes_digest(self, limit: int = 20) -> str:
        notes = self.notes()[-limit:]
        if not notes:
            return ""
        lines = [f"- [{n['topic']}] {n['content']}" for n in notes]
        return "# Session notes so far\n" + "\n".join(lines)
