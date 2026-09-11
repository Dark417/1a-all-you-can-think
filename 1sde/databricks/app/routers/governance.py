"""Governance & Lineage -- the Unity Catalog observability surface.

Unity Catalog automatically captures **data lineage** (which tables feed which)
across notebooks, jobs and pipelines, plus an **audit log** of queries and a view
of all **grants**. These endpoints expose:

  * the lineage graph (nodes + edges) recorded by the medallion/DLT/Auto Loader
    routers,
  * upstream sources of any table,
  * query history (the audit trail),
  * and a grants summary.
"""
from __future__ import annotations

from fastapi import APIRouter

from ..core.catalog import Collections, get_db
from ..core.lineage import graph, upstream
from ..core.naming import normalize_fqn

router = APIRouter(prefix="/governance", tags=["11. Governance & Lineage"])


@router.get("/lineage", summary="Unity Catalog data lineage graph (nodes + edges)")
def lineage():
    g = graph()
    g["note"] = "Edges are recorded automatically by medallion / DLT / Auto Loader runs."
    return g


@router.get("/lineage/{fqn}/upstream", summary="All tables transitively upstream of a table")
def lineage_upstream(fqn: str):
    fqn = normalize_fqn(fqn)
    return {"table": fqn, "upstream": upstream(fqn)}


@router.get("/query-history", summary="Audit: recent query history (with DBUs)")
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


@router.get("/grants-summary", summary="Summary of all grants by principal")
def grants_summary():
    db = get_db()
    by_principal: dict[str, list] = {}
    for g in db[Collections.GRANTS].find():
        by_principal.setdefault(g["principal"], []).append(
            {
                "privilege": g["privilege"],
                "on_type": g["securable_type"],
                "on_name": g["securable_name"],
            }
        )
    return {"principals": by_principal}


@router.delete("/result-cache", summary="Flush the Databricks SQL result cache")
def flush_cache():
    n = get_db()[Collections.RESULT_CACHE].count_documents({})
    get_db()[Collections.RESULT_CACHE].delete_many({})
    return {"status": "flushed", "entries_removed": n}
