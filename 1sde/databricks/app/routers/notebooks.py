"""Notebooks -- run a sequence of SQL/Python cells on a cluster.

A Databricks notebook is a list of cells; each runs on an **attached cluster**.
Here a notebook is registered as an ordered list of cells:

  * **SQL cells** execute on the cluster via DuckDB (DBSQL), metering DBUs.
  * **Python cells** ``exec`` in a persistent per-run sandbox namespace, so later
    cells can see variables defined by earlier ones (like notebook state). A
    ``result`` variable, if set, is captured as the cell output.

We return per-cell outputs, mirroring the notebook execution model.
"""
from __future__ import annotations

import contextlib
import io

from fastapi import APIRouter, HTTPException

from ..core.catalog import Collections, get_db
from ..core.engine import get_engine, utcnow
from ..models import NotebookCreate, NotebookRun

router = APIRouter(prefix="/notebooks", tags=["9. Notebooks"])


@router.post("", summary="Register a notebook (list of cells)")
def create_notebook(body: NotebookCreate):
    db = get_db()
    if db[Collections.NOTEBOOKS].find_one({"_id": body.name}):
        raise HTTPException(409, f"Notebook '{body.name}' already exists.")
    db[Collections.NOTEBOOKS].insert_one(
        {
            "_id": body.name,
            "cells": [c.model_dump() for c in body.cells],
            "created_at": utcnow(),
        }
    )
    return {"status": "created", "notebook": body.name, "cell_count": len(body.cells)}


@router.get("", summary="List notebooks")
def list_notebooks():
    return [
        {"name": n["_id"], "cells": len(n["cells"])}
        for n in get_db()[Collections.NOTEBOOKS].find()
    ]


@router.post("/{name}/run", summary="Execute the notebook cell-by-cell on a cluster")
def run_notebook(name: str, body: NotebookRun):
    nb = get_db()[Collections.NOTEBOOKS].find_one({"_id": name})
    if not nb:
        raise HTTPException(404, "Notebook not found")
    eng = get_engine()
    ns: dict = {}  # persistent Python namespace across cells
    outputs = []

    for i, cell in enumerate(nb["cells"]):
        if cell["language"] == "sql":
            try:
                res = eng.run(cell["source"], cluster=body.cluster, use_cache=False)
                outputs.append(
                    {"cell": i, "language": "sql", "status": "ok",
                     "columns": res["columns"], "rows": res["rows"][:50],
                     "row_count": res["row_count"], "dbus_used": res["dbus_used"]}
                )
            except Exception as exc:  # noqa: BLE001
                outputs.append({"cell": i, "language": "sql", "status": "error", "error": str(exc)})
        else:  # python
            stdout = io.StringIO()
            try:
                with contextlib.redirect_stdout(stdout):
                    exec(cell["source"], ns)  # noqa: S102 - intentional sandbox exec
                outputs.append(
                    {"cell": i, "language": "python", "status": "ok",
                     "stdout": stdout.getvalue(),
                     "result": _safe(ns.get("result"))}
                )
            except Exception as exc:  # noqa: BLE001
                outputs.append(
                    {"cell": i, "language": "python", "status": "error",
                     "stdout": stdout.getvalue(), "error": str(exc)}
                )

    return {"notebook": name, "cells_run": len(outputs), "outputs": outputs}


def _safe(v):
    try:
        import json

        json.dumps(v)
        return v
    except Exception:  # noqa: BLE001
        return repr(v)
