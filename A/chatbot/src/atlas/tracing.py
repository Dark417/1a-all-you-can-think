"""JSONL session tracing. One file per session under data/traces/.

Every event is a single JSON object on its own line — easy to tail,
easy to diff, no DB needed. This is the local equivalent of LangSmith /
Langfuse from tutorial 03."""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from .config import settings


def _serializable(obj: Any) -> Any:
    """Best-effort coercion so SDK objects (pydantic models, dataclasses, etc.)
    survive json.dumps."""
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if hasattr(obj, "dict") and callable(obj.dict):
        try:
            return obj.dict()
        except Exception:
            pass
    if isinstance(obj, (list, tuple)):
        return [_serializable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _serializable(v) for k, v in obj.items()}
    return obj


class Tracer:
    def __init__(self, session_id: str | None = None) -> None:
        self.session_id = session_id or uuid.uuid4().hex[:12]
        settings.trace_dir.mkdir(parents=True, exist_ok=True)
        self.path = settings.trace_dir / f"session-{self.session_id}.jsonl"

    def log(self, event_type: str, data: Any) -> None:
        record = {
            "ts": time.time(),
            "session_id": self.session_id,
            "event": event_type,
            "data": _serializable(data),
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")
