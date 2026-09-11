"""Time Travel + Zero-Copy Cloning.

Because storage is immutable micro-partitions, Snowflake can:
  * Query a table AS OF a past version/timestamp (Time Travel).
  * UNDROP a dropped object.
  * CLONE a table/schema/database instantly with no data copy -- the clone just
    references the same micro-partitions until one side is modified.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..core.catalog import Collections, get_db
from ..core.engine import get_engine, utcnow
from ..core.history import snapshot_table, version_at, versions
from ..core.naming import normalize_fqn, phys_table
from ..models import CloneRequest

router = APIRouter(prefix="/time-travel", tags=["8. Time Travel & Cloning"])


@router.get("/{fqn}/history", summary="Show version history of a table")
def history(fqn: str):
    fqn = normalize_fqn(fqn)
    if not get_db()[Collections.TABLES].find_one({"_id": fqn}):
        raise HTTPException(404, "Table not found")
    return {"table": fqn, "versions": versions(fqn)}


@router.get("/{fqn}/at", summary="SELECT ... AT (VERSION => n) | BEFORE (TIMESTAMP => t)")
def query_at(
    fqn: str,
    version: int | None = Query(None, description="Reconstruct this exact version."),
    before_timestamp: str | None = Query(None, description="ISO ts; latest version at/<= it."),
):
    fqn = normalize_fqn(fqn)
    snap = version_at(fqn, version=version, before_ts=before_timestamp)
    if not snap:
        raise HTTPException(404, "No snapshot for that point in time")
    return {
        "table": fqn,
        "version": snap["version"],
        "as_of": snap["timestamp"].isoformat(),
        "columns": snap["columns"],
        "rows": snap["rows"],
        "row_count": snap["row_count"],
    }


@router.post("/{fqn}/restore", summary="Restore a table to a previous version")
def restore(fqn: str, version: int):
    fqn = normalize_fqn(fqn)
    snap = version_at(fqn, version=version)
    if not snap:
        raise HTTPException(404, "No such version")
    eng = get_engine()
    eng.con.execute(f"DELETE FROM {phys_table(fqn)}")
    if snap["rows"]:
        eng.con.register("_restore_df", _to_arrow(snap["columns"], snap["rows"]))
        eng.con.execute(f"INSERT INTO {phys_table(fqn)} BY NAME SELECT * FROM _restore_df")
        eng.con.unregister("_restore_df")
    new_v = snapshot_table(fqn, f"RESTORE_FROM_V{version}")
    return {"status": "restored", "table": fqn, "restored_from": version, "new_version": new_v}


@router.post("/clone", summary="CREATE TABLE ... CLONE (zero-copy)")
def clone(body: CloneRequest):
    src = normalize_fqn(body.source)
    tgt = normalize_fqn(body.target)
    db = get_db()
    src_meta = db[Collections.TABLES].find_one({"_id": src})
    if not src_meta:
        raise HTTPException(404, f"Source table '{src}' not found")
    if db[Collections.TABLES].find_one({"_id": tgt}):
        raise HTTPException(409, f"Target '{tgt}' already exists")

    eng = get_engine()
    # CTAS copies in DuckDB; conceptually this is the "copy-on-write" moment.
    eng.con.execute(f"CREATE TABLE {phys_table(tgt)} AS SELECT * FROM {phys_table(src)}")
    db[Collections.TABLES].insert_one(
        {
            "_id": tgt,
            "database": tgt.split(".")[0],
            "schema": tgt.split(".")[1],
            "name": tgt.split(".")[2],
            "columns": src_meta["columns"],
            "track_time_travel": src_meta.get("track_time_travel", True),
            "version": 0,
            "cloned_from": src,
            "created_at": utcnow(),
        }
    )
    db[Collections.CLONES].insert_one({"source": src, "target": tgt, "at": utcnow()})
    snapshot_table(tgt, f"CLONE_OF_{src}")
    return {"status": "cloned", "source": src, "target": tgt, "note": "zero-copy; diverges on write"}


def _to_arrow(columns, rows):
    import pyarrow as pa

    cols = {c: [r.get(c) for r in rows] for c in columns}
    return pa.table(cols)
