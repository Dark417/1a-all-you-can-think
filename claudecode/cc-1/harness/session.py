"""Session management: every run is durable and resumable.

Layout on disk (sessions/<id>/):

    state.json      status, task, provider, result, agent tree
    events.jsonl    the full event stream, one JSON object per line —
                    this is the transcript, append-only, replayable
    workspace/      a private copy of the playground the agents mutate
    notes.json      the session memory store (written by memory.py)

Two properties worth copying into any harness:

  - The transcript is the source of truth. state.json is derived and
    disposable; events.jsonl is what lets a UI attach late, a crashed run be
    inspected, or a session be resumed.

  - Each session gets its own workspace copy, so runs are reproducible and
    two sessions can never trample each other's files.
"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

from .events import EventBus


class Session:
    def __init__(self, root: Path, session_id: str | None = None) -> None:
        self.id = session_id or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        self.dir = Path(root) / self.id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.workspace = self.dir / "workspace"
        self.bus = EventBus()
        self._events_file = (self.dir / "events.jsonl").open("a")
        self.bus.subscribe(self._persist_event, replay=False)
        self.state: dict[str, Any] = {
            "id": self.id, "status": "created", "task": None, "provider": None,
            "created": time.time(), "finished": None, "result": None, "agents": [],
        }

    def seed_workspace(self, playground: Path) -> None:
        if not self.workspace.exists():
            shutil.copytree(playground, self.workspace)

    def _persist_event(self, event) -> None:
        self._events_file.write(event.to_json() + "\n")
        self._events_file.flush()

    def update(self, **fields: Any) -> None:
        self.state.update(fields)
        # Atomic write: the UI's SSE thread reads this file concurrently, and a
        # plain write_text lets it observe a half-written (torn) JSON file.
        target = self.dir / "state.json"
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.state, indent=2, ensure_ascii=False))
        tmp.replace(target)

    def close(self) -> None:
        self._events_file.close()


class SessionStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def new(self) -> Session:
        return Session(self.root)

    def list(self) -> list[dict[str, Any]]:
        out = []
        for state_file in sorted(self.root.glob("*/state.json"), reverse=True):
            try:
                out.append(json.loads(state_file.read_text()))
            except json.JSONDecodeError:
                continue
        return out

    def load_state(self, session_id: str) -> dict[str, Any] | None:
        state_file = self.root / session_id / "state.json"
        if not state_file.exists():
            return None
        try:
            return json.loads(state_file.read_text())
        except json.JSONDecodeError:
            return None  # caller retries; never let a torn read propagate

    def load_events(self, session_id: str, after_seq: int = 0) -> list[dict[str, Any]]:
        events_file = self.root / session_id / "events.jsonl"
        if not events_file.exists():
            return []
        events = []
        for line in events_file.read_text().splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("seq", 0) > after_seq:
                events.append(event)
        return events

    def resume_brief(self, session_id: str) -> str:
        """Build the context brief a resumed session starts from: final state
        plus session notes — NOT the raw transcript (that is what compaction
        and notes are for)."""
        state = self.load_state(session_id)
        if not state:
            return ""
        notes_file = self.root / session_id / "notes.json"
        notes = json.loads(notes_file.read_text()) if notes_file.exists() else []
        note_lines = "\n".join(f"- [{n['topic']}] {n['content']}" for n in notes)
        return (
            f"Resuming session {session_id}.\n"
            f"Previous task: {state.get('task')}\n"
            f"Previous outcome: {str(state.get('result'))[:500]}\n"
            f"Notes carried forward:\n{note_lines or '- (none)'}"
        )
