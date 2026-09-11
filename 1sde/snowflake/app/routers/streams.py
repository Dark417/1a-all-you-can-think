"""Streams = Change Data Capture.

A Snowflake stream records a *change offset* on a table. Reading the stream
returns the rows inserted/updated/deleted since the offset; advancing the
offset (typically inside a DML transaction) "consumes" those changes. We derive
changes by diffing the time-travel snapshots captured by ``core.history``.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core.catalog import Collections, get_db
from ..core.engine import utcnow
from ..core.history import version_at, versions
from ..core.naming import normalize_fqn
from ..models import StreamCreate

router = APIRouter(prefix="/streams", tags=["6. Streams (CDC)"])


@router.post("", summary="CREATE STREAM ON TABLE")
def create_stream(body: StreamCreate):
    db = get_db()
    table = normalize_fqn(body.on_table)
    meta = db[Collections.TABLES].find_one({"_id": table})
    if not meta:
        raise HTTPException(404, f"Table '{table}' not found")
    if db[Collections.STREAMS].find_one({"_id": body.name}):
        raise HTTPException(409, "Stream already exists")
    db[Collections.STREAMS].insert_one(
        {"_id": body.name, "table": table, "offset_version": meta.get("version", 0), "created_at": utcnow()}
    )
    return {"status": "created", "stream": body.name, "offset_version": meta.get("version", 0)}


@router.get("/{name}", summary="SELECT * FROM <stream> (pending changes)")
def read_stream(name: str):
    return _changes(name)


@router.post("/{name}/consume", summary="Advance offset (consume changes)")
def consume(name: str):
    db = get_db()
    stream = db[Collections.STREAMS].find_one({"_id": name})
    if not stream:
        raise HTTPException(404, "Stream not found")
    changes = _changes(name)
    latest = db[Collections.TABLES].find_one({"_id": stream["table"]}).get("version", 0)
    db[Collections.STREAMS].update_one({"_id": name}, {"$set": {"offset_version": latest}})
    return {"status": "consumed", "consumed_changes": changes["change_count"], "new_offset": latest}


def _changes(name: str) -> dict:
    db = get_db()
    stream = db[Collections.STREAMS].find_one({"_id": name})
    if not stream:
        raise HTTPException(404, "Stream not found")
    table = stream["table"]
    offset = stream["offset_version"]
    latest = db[Collections.TABLES].find_one({"_id": table}).get("version", 0)

    old = version_at(table, version=offset)
    new = version_at(table, version=latest)
    old_rows = {_key(r): r for r in (old["rows"] if old else [])}
    new_rows = {_key(r): r for r in (new["rows"] if new else [])}

    changes = []
    for k, r in new_rows.items():
        if k not in old_rows:
            changes.append({"METADATA$ACTION": "INSERT", "METADATA$ISUPDATE": False, **r})
        elif old_rows[k] != r:
            changes.append({"METADATA$ACTION": "INSERT", "METADATA$ISUPDATE": True, **r})
    for k, r in old_rows.items():
        if k not in new_rows:
            changes.append({"METADATA$ACTION": "DELETE", "METADATA$ISUPDATE": False, **r})

    return {
        "stream": name,
        "table": table,
        "from_version": offset,
        "to_version": latest,
        "change_count": len(changes),
        "changes": changes,
        "history": versions(table),
    }


def _key(row: dict):
    """Stable identity for a row -- prefer an 'id'-like column, else whole row."""
    for cand in ("ID", "id", "Id"):
        if cand in row:
            return ("pk", row[cand])
    return ("full", tuple(sorted((str(k), str(v)) for k, v in row.items())))
