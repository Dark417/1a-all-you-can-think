"""Two memory components:

- `ConversationMemory` — short-term: in-memory list of Anthropic-format
  messages, with rolling truncation when the history exceeds the cap.
- `NoteStore` — long-term: SQLite-backed user notes (id, ts, content,
  tags). Persists across sessions."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import settings


# ---------- short-term -----------------------------------------------------


@dataclass
class ConversationMemory:
    """Holds Anthropic Messages-API formatted turns: each item is
    {"role": "user" | "assistant", "content": str | list[block]}."""

    max_turns: int = settings.history_max_turns
    messages: list[dict[str, Any]] = field(default_factory=list)

    def append(self, message: dict[str, Any]) -> None:
        self.messages.append(message)
        self._truncate()

    def extend(self, messages: list[dict[str, Any]]) -> None:
        self.messages.extend(messages)
        self._truncate()

    def compose(self) -> list[dict[str, Any]]:
        return list(self.messages)

    def clear(self) -> None:
        self.messages.clear()

    def _truncate(self) -> None:
        # A "turn" is user→assistant; cap roughly at 2 * max_turns messages.
        # We must NOT split a tool_use / tool_result pair: an assistant
        # message containing tool_use blocks must be immediately followed
        # by a user message with the matching tool_result blocks.
        cap = self.max_turns * 2
        if len(self.messages) <= cap:
            return
        cut = len(self.messages) - cap
        # Walk forward from `cut` to avoid orphaning a tool_result.
        while cut < len(self.messages) and self._is_orphan_tool_result(cut):
            cut += 1
        self.messages = self.messages[cut:]

    def _is_orphan_tool_result(self, idx: int) -> bool:
        msg = self.messages[idx]
        if msg.get("role") != "user":
            return False
        content = msg.get("content")
        if not isinstance(content, list):
            return False
        return any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        )


# ---------- long-term ------------------------------------------------------


SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  ts        REAL    NOT NULL,
  content   TEXT    NOT NULL,
  tags      TEXT    NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_notes_ts ON notes(ts DESC);
"""


@dataclass
class Note:
    id: int
    ts: float
    content: str
    tags: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "ts": self.ts, "content": self.content, "tags": self.tags}


class NoteStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.path = db_path or settings.notes_db
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def save(self, content: str, tags: list[str] | None = None) -> Note:
        ts = time.time()
        tags = tags or []
        cur = self._conn.execute(
            "INSERT INTO notes (ts, content, tags) VALUES (?, ?, ?)",
            (ts, content, json.dumps(tags)),
        )
        self._conn.commit()
        return Note(id=int(cur.lastrowid), ts=ts, content=content, tags=tags)

    def list(self, tag: str | None = None, limit: int = 10) -> list[Note]:
        limit = max(1, min(limit, 200))
        if tag:
            rows = self._conn.execute(
                "SELECT id, ts, content, tags FROM notes "
                "WHERE tags LIKE ? ORDER BY ts DESC LIMIT ?",
                (f'%"{tag}"%', limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, ts, content, tags FROM notes ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [Note(id=r[0], ts=r[1], content=r[2], tags=json.loads(r[3])) for r in rows]

    def delete(self, note_id: int) -> bool:
        cur = self._conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()
