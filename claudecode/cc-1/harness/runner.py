"""Glue: one function that runs a task inside a fresh session.

Shared by the CLI, the smoke test, and the FastAPI server so all three
surfaces exercise the identical code path.
"""

from __future__ import annotations

from pathlib import Path

from .orchestrator import Orchestrator
from .providers import make_provider
from .session import Session, SessionStore

CC1_ROOT = Path(__file__).resolve().parents[1]
PLAYGROUND = CC1_ROOT / "playground"
SESSIONS_ROOT = CC1_ROOT / "sessions"


def run_task(task: str, provider_name: str = "mock",
             store: SessionStore | None = None,
             resume_from: str | None = None,
             on_event=None) -> Session:
    store = store or SessionStore(SESSIONS_ROOT)
    session = store.new()
    session.seed_workspace(PLAYGROUND)
    if on_event is not None:
        session.bus.subscribe(on_event, replay=False)

    if resume_from:
        brief = store.resume_brief(resume_from)
        if brief:
            task = f"{brief}\n\nNew request: {task}"

    provider = make_provider(provider_name)
    orchestrator = Orchestrator(session.workspace, session.dir, provider, session.bus)
    session.update(status="running", task=task, provider=provider_name)
    session.bus.emit("session.started", task=task, provider=provider_name, session_id=session.id)

    try:
        orchestrator.start()
        result = orchestrator.run_task(task)
        session.update(status="completed", result=result.text,
                       agents=orchestrator.tree(), finished=__import__("time").time())
        session.bus.emit("session.completed", result=result.text[:600])
    except Exception as exc:
        session.update(status="failed", result=f"error: {exc}",
                       agents=orchestrator.tree(), finished=__import__("time").time())
        session.bus.emit("session.failed", error=str(exc))
        raise
    finally:
        orchestrator.shutdown()
        session.close()
    return session
