"""Tasks = scheduled SQL + task DAGs.

A *root* task runs on a schedule; *child* tasks run AFTER a parent, forming a
DAG (the building block of declarative pipelines). We back the schedule with
APScheduler and run each task on its warehouse, recording run history.
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import APIRouter, HTTPException

from ..core.catalog import Collections, get_db
from ..core.engine import get_engine, utcnow
from ..models import TaskCreate

router = APIRouter(prefix="/tasks", tags=["7. Tasks (scheduled DAGs)"])

_scheduler = BackgroundScheduler(daemon=True)
_scheduler.start()


@router.post("", summary="CREATE TASK")
def create_task(body: TaskCreate):
    db = get_db()
    if db[Collections.TASKS].find_one({"_id": body.name}):
        raise HTTPException(409, "Task already exists")
    if body.after and not db[Collections.TASKS].find_one({"_id": body.after}):
        raise HTTPException(404, f"Parent task '{body.after}' not found")
    db[Collections.TASKS].insert_one(
        {
            "_id": body.name,
            "sql": body.sql,
            "warehouse": body.warehouse,
            "schedule_seconds": body.schedule_seconds,
            "after": body.after,
            "state": "SUSPENDED",  # Snowflake tasks start suspended
            "runs": [],
            "created_at": utcnow(),
        }
    )
    return {"status": "created", "task": body.name, "state": "SUSPENDED"}


@router.post("/{name}/resume", summary="ALTER TASK ... RESUME (start scheduling)")
def resume(name: str):
    task = _require(name)
    get_db()[Collections.TASKS].update_one({"_id": name}, {"$set": {"state": "STARTED"}})
    if task.get("schedule_seconds"):
        _scheduler.add_job(
            _run_task_tree,
            "interval",
            seconds=task["schedule_seconds"],
            args=[name],
            id=name,
            replace_existing=True,
            max_instances=1,
        )
    return {"status": "resumed", "task": name}


@router.post("/{name}/suspend", summary="ALTER TASK ... SUSPEND")
def suspend(name: str):
    _require(name)
    get_db()[Collections.TASKS].update_one({"_id": name}, {"$set": {"state": "SUSPENDED"}})
    try:
        _scheduler.remove_job(name)
    except Exception:  # noqa: BLE001
        pass
    return {"status": "suspended", "task": name}


@router.post("/{name}/run", summary="EXECUTE TASK (run now, incl. child DAG)")
def run_now(name: str):
    _require(name)
    return {"status": "executed", "results": _run_task_tree(name)}


@router.get("", summary="SHOW TASKS")
def list_tasks():
    return [
        {
            "name": t["_id"],
            "state": t["state"],
            "schedule_seconds": t.get("schedule_seconds"),
            "after": t.get("after"),
            "run_count": len(t.get("runs", [])),
        }
        for t in get_db()[Collections.TASKS].find()
    ]


@router.get("/{name}/history", summary="Task run history")
def history(name: str):
    return {"task": name, "runs": _require(name).get("runs", [])[-20:]}


# --------------------------------------------------------------------------- #
def _run_task_tree(name: str) -> list[dict]:
    """Run a task, then recursively run all children (the DAG)."""
    results = [_run_single(name)]
    for child in get_db()[Collections.TASKS].find({"after": name, "state": "STARTED"}):
        results.extend(_run_task_tree(child["_id"]))
    return results


def _run_single(name: str) -> dict:
    db = get_db()
    task = db[Collections.TASKS].find_one({"_id": name})
    started = utcnow()
    try:
        res = get_engine().run(task["sql"], warehouse=task["warehouse"])
        run = {"started_at": started.isoformat(), "state": "SUCCEEDED", "rows": res["row_count"]}
    except Exception as exc:  # noqa: BLE001
        run = {"started_at": started.isoformat(), "state": "FAILED", "error": str(exc)}
    db[Collections.TASKS].update_one({"_id": name}, {"$push": {"runs": run}})
    return {"task": name, **run}


def _require(name: str) -> dict:
    t = get_db()[Collections.TASKS].find_one({"_id": name})
    if not t:
        raise HTTPException(404, "Task not found")
    return t
