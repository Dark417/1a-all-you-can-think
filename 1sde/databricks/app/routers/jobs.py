"""Jobs / Workflows -- multi-task orchestration DAGs.

Databricks **Workflows** run **jobs** made of multiple **tasks** with
``depends_on`` edges forming a DAG. A job can be triggered on a **schedule** (we
use APScheduler) or **run now**, and each run records per-task status.

This is the Databricks counterpart to Snowflake Tasks, but a single job owns
*many* tasks with dependencies (rather than one statement per task object).
"""
from __future__ import annotations

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import APIRouter, HTTPException

from ..core.catalog import Collections, get_db
from ..core.engine import get_engine, utcnow
from ..models import JobCreate

router = APIRouter(prefix="/jobs", tags=["8. Jobs / Workflows"])

_scheduler = BackgroundScheduler(daemon=True)
_scheduler.start()


@router.post("", summary="Create a job (multi-task DAG)")
def create_job(body: JobCreate):
    db = get_db()
    if db[Collections.JOBS].find_one({"_id": body.name}):
        raise HTTPException(409, f"Job '{body.name}' already exists.")
    keys = {t.key for t in body.tasks}
    for t in body.tasks:
        for dep in t.depends_on:
            if dep not in keys:
                raise HTTPException(400, f"Task '{t.key}' depends on unknown task '{dep}'.")
    db[Collections.JOBS].insert_one(
        {
            "_id": body.name,
            "tasks": [t.model_dump() for t in body.tasks],
            "cluster": body.cluster,
            "schedule_seconds": body.schedule_seconds,
            "runs": [],
            "created_at": utcnow(),
        }
    )
    if body.schedule_seconds:
        _scheduler.add_job(
            _execute_job,
            "interval",
            seconds=body.schedule_seconds,
            args=[body.name],
            id=body.name,
            replace_existing=True,
            max_instances=1,
        )
    return {"status": "created", "job": body.name, "tasks": [t.key for t in body.tasks]}


@router.get("", summary="List jobs")
def list_jobs():
    return [
        {
            "name": j["_id"],
            "tasks": [t["key"] for t in j["tasks"]],
            "schedule_seconds": j.get("schedule_seconds"),
            "run_count": len(j.get("runs", [])),
        }
        for j in get_db()[Collections.JOBS].find()
    ]


@router.post("/{name}/run", summary="Run the job now (executes the task DAG)")
def run_now(name: str):
    _require(name)
    return _execute_job(name)


@router.get("/{name}/runs", summary="Run history (per-task status)")
def runs(name: str):
    return {"job": name, "runs": _require(name).get("runs", [])[-20:]}


# --------------------------------------------------------------------------- #
def _execute_job(name: str) -> dict:
    db = get_db()
    job = db[Collections.JOBS].find_one({"_id": name})
    tasks = {t["key"]: t for t in job["tasks"]}
    order = _toposort(tasks)
    eng = get_engine()
    started = utcnow()

    task_results = []
    state = "SUCCEEDED"
    for key in order:
        task = tasks[key]
        # Skip if any upstream task failed (mirrors Workflows' default behaviour).
        upstream_failed = any(
            tr["state"] == "FAILED" for tr in task_results if tr["task"] in task["depends_on"]
        )
        if upstream_failed:
            task_results.append({"task": key, "state": "SKIPPED"})
            state = "FAILED"
            continue
        try:
            res = eng.run(task["sql"], cluster=job["cluster"], use_cache=False)
            task_results.append({"task": key, "state": "SUCCEEDED", "rows": res["row_count"]})
        except Exception as exc:  # noqa: BLE001
            task_results.append({"task": key, "state": "FAILED", "error": str(exc)})
            state = "FAILED"

    run = {
        "started_at": started.isoformat(),
        "ended_at": utcnow().isoformat(),
        "state": state,
        "run_order": order,
        "tasks": task_results,
    }
    db[Collections.JOBS].update_one({"_id": name}, {"$push": {"runs": run}})
    return {"job": name, **run}


def _toposort(tasks: dict) -> list[str]:
    order: list[str] = []
    visited: set[str] = set()
    temp: set[str] = set()

    def visit(n: str):
        if n in visited:
            return
        if n in temp:
            raise HTTPException(400, f"Cycle detected at task '{n}'.")
        temp.add(n)
        for dep in tasks[n]["depends_on"]:
            visit(dep)
        temp.discard(n)
        visited.add(n)
        order.append(n)

    for n in tasks:
        visit(n)
    return order


def _require(name: str) -> dict:
    j = get_db()[Collections.JOBS].find_one({"_id": name})
    if not j:
        raise HTTPException(404, "Job not found")
    return j
