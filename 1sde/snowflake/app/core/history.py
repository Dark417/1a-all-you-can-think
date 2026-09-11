"""Time-travel + change-tracking primitives shared by the tables, streams and
time-travel routers.

Snowflake keeps immutable micro-partitions, so any past version of a table can
be reconstructed for the retention window (Time Travel) and CDC can be derived
by diffing versions (Streams). We emulate that by snapshotting a table's full
row set into MongoDB on every mutation, tagged with a monotonically increasing
version and timestamp.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .catalog import Collections, get_db
from .engine import get_engine
from .naming import normalize_fqn, phys_table


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def snapshot_table(fqn: str, change_type: str) -> int:
    """Persist the current full contents of ``fqn`` as a new version.

    Returns the new version number. ``change_type`` is informational
    (INSERT/UPDATE/DELETE/CREATE/LOAD).
    """
    fqn = normalize_fqn(fqn)
    db = get_db()
    meta = db[Collections.TABLES].find_one({"_id": fqn})
    if not meta or not meta.get("track_time_travel", True):
        return -1

    eng = get_engine()
    cur = eng.con.execute(f"SELECT * FROM {phys_table(fqn)}")
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, _row(r))) for r in cur.fetchall()]

    version = meta.get("version", 0) + 1
    db[Collections.TIME_TRAVEL].insert_one(
        {
            "table": fqn,
            "version": version,
            "change_type": change_type,
            "timestamp": utcnow(),
            "columns": cols,
            "rows": rows,
            "row_count": len(rows),
        }
    )
    db[Collections.TABLES].update_one({"_id": fqn}, {"$set": {"version": version}})
    return version


def versions(fqn: str) -> list[dict[str, Any]]:
    fqn = normalize_fqn(fqn)
    out = []
    for v in get_db()[Collections.TIME_TRAVEL].find({"table": fqn}).sort("version", 1):
        out.append(
            {
                "version": v["version"],
                "change_type": v["change_type"],
                "timestamp": v["timestamp"].isoformat(),
                "row_count": v["row_count"],
            }
        )
    return out


def version_at(fqn: str, version: int | None = None, before_ts: str | None = None) -> dict | None:
    """Return the snapshot AT a version, or the latest one BEFORE a timestamp."""
    fqn = normalize_fqn(fqn)
    q = get_db()[Collections.TIME_TRAVEL]
    if version is not None:
        return q.find_one({"table": fqn, "version": version})
    if before_ts is not None:
        ts = datetime.fromisoformat(before_ts)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        snaps = list(q.find({"table": fqn, "timestamp": {"$lte": ts}}).sort("version", -1).limit(1))
        return snaps[0] if snaps else None
    return q.find({"table": fqn}).sort("version", -1).limit(1)[0]


def _row(r):
    out = []
    for v in r:
        if isinstance(v, (datetime,)):
            out.append(v.isoformat())
        else:
            out.append(v)
    return out
