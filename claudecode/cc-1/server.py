"""HTTP/SSE bridge: the harness for the Angular watchtower UI.

    python3 server.py          # http://localhost:8100

Endpoints:
    GET  /api/health
    GET  /api/sessions                  list past + running sessions
    POST /api/sessions {task,provider}  start a run in a worker thread
    GET  /api/sessions/{id}             state snapshot (agents, result)
    GET  /api/sessions/{id}/events      SSE: replay + live event stream

Design note: the server owns nothing the CLI does not — it subscribes to the
same EventBus and reads the same JSONL/state files. A UI is just another
event consumer.
"""

from __future__ import annotations

import json
import queue
import threading
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from harness.runner import SESSIONS_ROOT, run_task
from harness.session import SessionStore

app = FastAPI(title="cc-1 harness")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4300", "http://localhost:4200"],
    allow_methods=["*"], allow_headers=["*"],
)

store = SessionStore(SESSIONS_ROOT)

# session id -> list of live subscriber queues (for runs in progress)
_live: dict[str, list[queue.Queue]] = {}
_live_lock = threading.Lock()


class NewSession(BaseModel):
    task: str
    provider: str = "mock"
    resume_from: str | None = None


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "sessions": len(store.list())}


@app.get("/api/sessions")
def list_sessions() -> list[dict]:
    return store.list()


@app.post("/api/sessions", status_code=202)
def create_session(body: NewSession) -> dict:
    if not body.task.strip():
        raise HTTPException(422, "task is required")

    started = threading.Event()
    holder: dict = {}

    def fanout(event) -> None:
        session_id = holder.get("id")
        if session_id is None:
            return
        with _live_lock:
            for q in _live.get(session_id, []):
                q.put(event.to_dict())

    def work() -> None:
        try:
            # run_task creates the Session; capture its id via the first event
            def capture(event):
                if "session_id" in event.data and "id" not in holder:
                    holder["id"] = event.data["session_id"]
                    started.set()
                fanout(event)
            run_task(body.task, provider_name=body.provider,
                     store=store, resume_from=body.resume_from, on_event=capture)
        except Exception:
            started.set()
        finally:
            with _live_lock:
                _live.pop(holder.get("id"), None)

    threading.Thread(target=work, daemon=True).start()
    if not started.wait(timeout=15) or "id" not in holder:
        raise HTTPException(500, "session failed to start")
    return {"id": holder["id"]}


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    state = store.load_state(session_id)
    if state is None:
        raise HTTPException(404, "no such session")
    return state


@app.get("/api/sessions/{session_id}/events")
def stream_events(session_id: str):
    """SSE: replay the persisted transcript, then follow live events."""
    if store.load_state(session_id) is None:
        raise HTTPException(404, "no such session")

    q: queue.Queue = queue.Queue()
    with _live_lock:
        _live.setdefault(session_id, []).append(q)

    def generate():
        last_seq = 0
        try:
            for event in store.load_events(session_id):
                last_seq = max(last_seq, event.get("seq", 0))
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            deadline_idle = time.time() + 3600
            while time.time() < deadline_idle:
                state = store.load_state(session_id) or {}
                try:
                    event = q.get(timeout=2.0)
                    if event.get("seq", 0) > last_seq:
                        last_seq = event["seq"]
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    continue
                except queue.Empty:
                    pass
                if state.get("status") in ("completed", "failed"):
                    # flush anything persisted after our replay, then finish
                    for event in store.load_events(session_id, after_seq=last_seq):
                        last_seq = event["seq"]
                        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'stream.end', 'seq': last_seq + 1, 'data': {}})}\n\n"
                    return
                yield ": keepalive\n\n"
        finally:
            with _live_lock:
                if q in _live.get(session_id, []):
                    _live[session_id].remove(q)

    return StreamingResponse(generate(), media_type="text/event-stream",
                             headers={"cache-control": "no-cache", "x-accel-buffering": "no"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8100, log_level="warning")
