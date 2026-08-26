"""The event bus: the harness's observability backbone.

Every interesting thing that happens — an agent turn, a tool call, an MCP
round-trip, a sub-agent spawn, a compaction — is emitted as an Event. The CLI
renders them to the terminal, the FastAPI server streams them to the Angular
UI over SSE, and the session manager persists them to JSONL. One producer
API, many consumers.

This is the same shape real harnesses use: the agent loop itself never
prints or persists anything; it only emits.
"""

from __future__ import annotations

import itertools
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class Event:
    seq: int
    ts: float
    type: str            # e.g. "agent.turn", "tool.call", "mcp.call", "compaction"
    agent_id: str | None # which agent produced it (None = harness-level)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "type": self.type,
            "agent_id": self.agent_id,
            "data": self.data,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


class EventBus:
    """Thread-safe pub/sub with replay.

    Subscribers get every past event on subscribe (so a UI that connects
    mid-run still sees the whole story) and every future one as it happens.
    """

    def __init__(self) -> None:
        self._events: list[Event] = []
        self._subscribers: list[Callable[[Event], None]] = []
        self._lock = threading.Lock()
        self._seq = itertools.count(1)

    def emit(self, type: str, agent_id: str | None = None, **data: Any) -> Event:
        event = Event(seq=next(self._seq), ts=time.time(), type=type, agent_id=agent_id, data=data)
        with self._lock:
            self._events.append(event)
            subscribers = list(self._subscribers)
        for callback in subscribers:
            try:
                callback(event)
            except Exception:
                pass  # a broken consumer must never break the agent loop
        return event

    def subscribe(self, callback: Callable[[Event], None], replay: bool = True) -> Callable[[], None]:
        with self._lock:
            past = list(self._events) if replay else []
            self._subscribers.append(callback)
        for event in past:
            callback(event)

        def unsubscribe() -> None:
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)

        return unsubscribe

    def all(self) -> list[Event]:
        with self._lock:
            return list(self._events)

    def since(self, seq: int) -> list[Event]:
        with self._lock:
            return [e for e in self._events if e.seq > seq]
