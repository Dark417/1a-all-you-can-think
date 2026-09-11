"""Clusters = elastic, independent compute (the Databricks analogue of
Snowflake warehouses).

Databricks compute comes in flavours:
  * **All-purpose clusters** for interactive/notebook work.
  * **Job clusters** spun up for a single job run and torn down after.
  * **SQL warehouses** for Databricks SQL (DBSQL).

All are billed in **DBUs** (Databricks Units) per second while RUNNING, scaled by
size and -- with **autoscaling** -- by the number of active workers. Here a
cluster is a logical object whose size sets DuckDB's thread budget; queries that
"run on" it (see the ``sql`` router) meter DBUs against it.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core.catalog import Collections, get_db
from ..core.engine import CLUSTER_DBU_RATE, CLUSTER_THREADS, utcnow
from ..models import ClusterCreate, ClusterResize

router = APIRouter(prefix="/clusters", tags=["1. Clusters (compute)"])


@router.post("", summary="Create a cluster")
def create_cluster(body: ClusterCreate):
    db = get_db()
    if db[Collections.CLUSTERS].find_one({"_id": body.name}):
        raise HTTPException(409, f"Cluster '{body.name}' already exists.")
    doc = {
        "_id": body.name,
        "size": body.size,
        "cluster_type": body.cluster_type,
        "state": "RUNNING",
        "autoscale": body.autoscale,
        "min_workers": body.min_workers,
        "max_workers": body.max_workers,
        "current_workers": body.min_workers,
        "photon": body.photon,
        "threads": CLUSTER_THREADS.get(body.size, 1),
        "dbus_used": 0.0,
        "query_count": 0,
        "dbu_rate_per_hour": round(CLUSTER_DBU_RATE[body.size] * 3600, 2),
        "created_at": utcnow(),
    }
    db[Collections.CLUSTERS].insert_one(doc)
    return {"status": "created", "cluster": _clean(doc)}


@router.get("", summary="List clusters")
def list_clusters():
    return [_clean(c) for c in get_db()[Collections.CLUSTERS].find()]


@router.post("/{name}/start", summary="Start (RUNNING) a terminated cluster")
def start(name: str):
    _update(name, {"state": "RUNNING", "started_at": utcnow()})
    return {"status": "running", "cluster": name}


@router.post("/{name}/terminate", summary="Terminate (stop billing) a cluster")
def terminate(name: str):
    _update(name, {"state": "TERMINATED", "terminated_at": utcnow()})
    return {"status": "terminated", "cluster": name}


@router.post("/{name}/resize", summary="Resize / reconfigure autoscaling")
def resize(name: str, body: ClusterResize):
    c = _require(name)
    fields: dict = {}
    if body.size:
        fields["size"] = body.size
        fields["threads"] = CLUSTER_THREADS.get(body.size, 1)
        fields["dbu_rate_per_hour"] = round(CLUSTER_DBU_RATE[body.size] * 3600, 2)
    if body.min_workers is not None:
        fields["min_workers"] = body.min_workers
    if body.max_workers is not None:
        fields["max_workers"] = body.max_workers
    if body.current_workers is not None:
        # Clamp to the (possibly updated) autoscaling bounds.
        lo = fields.get("min_workers", c.get("min_workers", 1))
        hi = fields.get("max_workers", c.get("max_workers", body.current_workers))
        fields["current_workers"] = max(lo, min(hi, body.current_workers))
    _update(name, fields)
    return {"status": "resized", "cluster": name, **fields}


@router.get("/{name}/usage", summary="DBUs consumed so far")
def usage(name: str):
    c = _require(name)
    return {
        "cluster": name,
        "size": c["size"],
        "state": c["state"],
        "current_workers": c.get("current_workers", c.get("min_workers", 1)),
        "dbus_used": round(c.get("dbus_used", 0.0), 8),
        "query_count": c.get("query_count", 0),
        "dbu_rate_per_hour": c.get("dbu_rate_per_hour"),
    }


@router.delete("/{name}", summary="Delete a cluster")
def delete(name: str):
    res = get_db()[Collections.CLUSTERS].delete_one({"_id": name})
    if not res.deleted_count:
        raise HTTPException(404, "No such cluster")
    return {"status": "deleted", "cluster": name}


def _require(name: str) -> dict:
    c = get_db()[Collections.CLUSTERS].find_one({"_id": name})
    if not c:
        raise HTTPException(404, "No such cluster")
    return c


def _update(name: str, fields: dict) -> None:
    res = get_db()[Collections.CLUSTERS].update_one({"_id": name}, {"$set": fields})
    if not res.matched_count:
        raise HTTPException(404, "No such cluster")


def _clean(doc: dict) -> dict:
    doc = dict(doc)
    doc["name"] = doc.pop("_id")
    doc.pop("created_at", None)
    return doc
