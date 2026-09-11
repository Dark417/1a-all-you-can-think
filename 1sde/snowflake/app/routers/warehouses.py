"""Virtual Warehouses = elastic, independent compute clusters.

Demonstrates the storage/compute separation: you can spin up many warehouses of
different sizes against the *same* data, suspend/resume them to stop billing,
and resize them on the fly.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core.catalog import Collections, get_db
from ..core.engine import WAREHOUSE_CREDIT_RATE, utcnow
from ..models import WarehouseCreate, WarehouseResize

router = APIRouter(prefix="/warehouses", tags=["1. Warehouses (compute)"])


@router.post("", summary="CREATE WAREHOUSE")
def create_warehouse(body: WarehouseCreate):
    db = get_db()
    if db[Collections.WAREHOUSES].find_one({"_id": body.name}):
        raise HTTPException(409, f"Warehouse '{body.name}' already exists.")
    doc = {
        "_id": body.name,
        "size": body.size,
        "state": "RUNNING",
        "auto_suspend_seconds": body.auto_suspend_seconds,
        "comment": body.comment,
        "credits_used": 0.0,
        "query_count": 0,
        "created_at": utcnow(),
        "credit_rate_per_hour": round(WAREHOUSE_CREDIT_RATE[body.size] * 3600, 2),
    }
    db[Collections.WAREHOUSES].insert_one(doc)
    return {"status": "created", "warehouse": _clean(doc)}


@router.get("", summary="SHOW WAREHOUSES")
def list_warehouses():
    return [_clean(w) for w in get_db()[Collections.WAREHOUSES].find()]


@router.post("/{name}/suspend", summary="ALTER WAREHOUSE ... SUSPEND")
def suspend(name: str):
    _update(name, {"state": "SUSPENDED", "suspended_at": utcnow()})
    return {"status": "suspended", "warehouse": name}


@router.post("/{name}/resume", summary="ALTER WAREHOUSE ... RESUME")
def resume(name: str):
    _update(name, {"state": "RUNNING", "resumed_at": utcnow()})
    return {"status": "resumed", "warehouse": name}


@router.post("/{name}/resize", summary="ALTER WAREHOUSE ... SET WAREHOUSE_SIZE")
def resize(name: str, body: WarehouseResize):
    _update(
        name,
        {
            "size": body.size,
            "credit_rate_per_hour": round(WAREHOUSE_CREDIT_RATE[body.size] * 3600, 2),
        },
    )
    return {"status": "resized", "warehouse": name, "size": body.size}


@router.get("/{name}/usage", summary="Credits consumed so far")
def usage(name: str):
    w = get_db()[Collections.WAREHOUSES].find_one({"_id": name})
    if not w:
        raise HTTPException(404, "No such warehouse")
    return {
        "warehouse": name,
        "size": w["size"],
        "state": w["state"],
        "credits_used": round(w.get("credits_used", 0.0), 8),
        "query_count": w.get("query_count", 0),
    }


@router.delete("/{name}", summary="DROP WAREHOUSE")
def drop(name: str):
    res = get_db()[Collections.WAREHOUSES].delete_one({"_id": name})
    if not res.deleted_count:
        raise HTTPException(404, "No such warehouse")
    return {"status": "dropped", "warehouse": name}


def _update(name: str, fields: dict):
    res = get_db()[Collections.WAREHOUSES].update_one({"_id": name}, {"$set": fields})
    if not res.matched_count:
        raise HTTPException(404, "No such warehouse")


def _clean(doc: dict) -> dict:
    doc = dict(doc)
    doc["name"] = doc.pop("_id")
    doc.pop("created_at", None)
    return doc
