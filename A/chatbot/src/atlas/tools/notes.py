"""Long-term memory exposed as two tools: save_note and list_notes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..memory import NoteStore
    from . import Tool


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def build_note_tools(store: "NoteStore") -> list["Tool"]:
    from . import Tool

    def save_handler(payload: dict[str, Any]) -> dict[str, Any]:
        content = (payload.get("content") or "").strip()
        if not content:
            return {"error": "content is required"}
        if len(content) > 4_000:
            return {"error": "content exceeds 4000 chars"}
        tags = payload.get("tags") or []
        if not isinstance(tags, list):
            return {"error": "tags must be a list of strings"}
        tags = [str(t).strip().lower() for t in tags if str(t).strip()][:8]
        note = store.save(content=content, tags=tags)
        return {"saved": True, "id": note.id, "ts": _fmt_ts(note.ts), "tags": note.tags}

    def list_handler(payload: dict[str, Any]) -> dict[str, Any]:
        tag = payload.get("tag")
        limit = int(payload.get("limit", 10))
        notes = store.list(tag=tag, limit=limit)
        return {
            "count": len(notes),
            "notes": [
                {"id": n.id, "ts": _fmt_ts(n.ts), "tags": n.tags, "content": n.content}
                for n in notes
            ],
        }

    save_tool = Tool(
        name="save_note",
        description=(
            "Persist a short note for the user, e.g. a fact they want remembered "
            "across sessions, a TODO, or a decision they made. Use sparingly — "
            "only when the user explicitly asks to remember something."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "The note body."},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional short tags (lowercase).",
                    "maxItems": 8,
                },
            },
            "required": ["content"],
        },
        handler=save_handler,
    )

    list_tool = Tool(
        name="list_notes",
        description=(
            "List recent user notes, optionally filtered by tag. Use when the "
            "user asks 'what have I told you to remember', 'show my notes', or "
            "when relevant context might be in prior notes."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "tag": {"type": "string", "description": "Optional tag filter."},
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
            },
        },
        handler=list_handler,
    )

    return [save_tool, list_tool]
