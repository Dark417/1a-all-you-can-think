"""Secure Data Sharing, Resource Monitors, Query History & Result Cache.

These are the "cloud services layer" features: governance and observability that
sit above compute and storage.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core.catalog import Collections, get_db
from ..core.engine import utcnow
from ..models import ResourceMonitorCreate, ShareCreate

router = APIRouter(prefix="/governance", tags=["11. Sharing, Monitors & History"])


# ----------------------------- Secure shares ------------------------------- #
@router.post("/shares", summary="CREATE SHARE (secure data sharing)")
def create_share(body: ShareCreate):
    db = get_db()
    if db[Collections.SHARES].find_one({"_id": body.name}):
        raise HTTPException(409, "Share exists")
    for obj in body.objects:
        if not db[Collections.TABLES].find_one({"_id": obj.upper()}):
            raise HTTPException(404, f"Object '{obj}' not found")
    db[Collections.SHARES].insert_one(
        {"_id": body.name, "objects": [o.upper() for o in body.objects], "accounts": body.accounts, "created_at": utcnow()}
    )
    return {
        "status": "created",
        "share": body.name,
        "note": "Consumers query a read-only reference -- no data is copied (live share).",
    }


@router.get("/shares", summary="SHOW SHARES")
def list_shares():
    return [
        {"name": s["_id"], "objects": s["objects"], "accounts": s["accounts"]}
        for s in get_db()[Collections.SHARES].find()
    ]


# --------------------------- Resource monitors ----------------------------- #
@router.post("/resource-monitors", summary="CREATE RESOURCE MONITOR")
def create_monitor(body: ResourceMonitorCreate):
    get_db()[Collections.RESOURCE_MONITORS].replace_one(
        {"_id": body.name},
        {
            "_id": body.name,
            "credit_quota": body.credit_quota,
            "on_breach": body.on_breach,
            "warehouses": body.warehouses,
            "created_at": utcnow(),
        },
        upsert=True,
    )
    return {"status": "created", "monitor": body.name}


@router.get("/resource-monitors/evaluate", summary="Evaluate quotas & enforce")
def evaluate_monitors():
    """Sum credits used by each monitor's warehouses; if over quota and policy is
    SUSPEND, suspend them -- mirroring Snowflake's spend guardrails."""
    db = get_db()
    actions = []
    for mon in db[Collections.RESOURCE_MONITORS].find():
        used = 0.0
        for wh in mon["warehouses"]:
            w = db[Collections.WAREHOUSES].find_one({"_id": wh})
            used += w.get("credits_used", 0.0) if w else 0.0
        breached = used >= mon["credit_quota"]
        if breached and mon["on_breach"] == "SUSPEND":
            for wh in mon["warehouses"]:
                db[Collections.WAREHOUSES].update_one(
                    {"_id": wh}, {"$set": {"state": "SUSPENDED", "suspended_by_monitor": mon["_id"]}}
                )
        actions.append(
            {
                "monitor": mon["_id"],
                "credits_used": round(used, 8),
                "quota": mon["credit_quota"],
                "breached": breached,
                "action": mon["on_breach"] if breached else "none",
            }
        )
    return {"evaluations": actions}


# ----------------------------- Query history ------------------------------- #
@router.get("/query-history", summary="QUERY_HISTORY view")
def query_history(limit: int = 50):
    rows = (
        get_db()[Collections.QUERY_HISTORY].find({}, {"_id": 0}).sort("started_at", -1).limit(limit)
    )
    out = []
    for r in rows:
        r["started_at"] = r["started_at"].isoformat()
        r["ended_at"] = r["ended_at"].isoformat()
        out.append(r)
    return {"queries": out}


@router.delete("/result-cache", summary="Flush the result cache")
def flush_cache():
    n = get_db()[Collections.RESULT_CACHE].count_documents({})
    get_db()[Collections.RESULT_CACHE].delete_many({})
    return {"status": "flushed", "entries_removed": n}
