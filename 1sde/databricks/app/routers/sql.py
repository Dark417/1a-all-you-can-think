"""Databricks SQL (DBSQL) -- run SQL on a cluster/SQL-warehouse via DuckDB.

DuckDB is our Photon-style vectorised engine. It reads the **real Delta tables**
directly through ``delta_scan('<path>')`` (the ``delta`` extension), so a query
sees exactly the committed Delta state. Tables to query are registered as views
under their ``catalog.schema.table`` name (dots -> ``__`` in the view id, since
DuckDB is 2-level).

Every query meters **DBUs** against its cluster, is recorded in query history,
and read-only queries are served from a **result cache** on repeat -- mirroring
Databricks SQL.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core.delta_io import table_exists
from ..core.engine import get_engine
from ..core.naming import normalize_fqn
from ..models import SqlRequest

router = APIRouter(prefix="/sql", tags=["4. Databricks SQL (DBSQL)"])


@router.post("", summary="Execute SQL on a cluster (reads Delta tables via views)")
def run_sql(body: SqlRequest):
    eng = get_engine()
    # Register any requested Delta tables as queryable views first.
    registered = {}
    for fqn in body.register:
        fqn = normalize_fqn(fqn)
        if not table_exists(fqn):
            raise HTTPException(404, f"Delta table '{fqn}' does not exist.")
        view = eng.register_delta(fqn)
        registered[fqn] = view
    try:
        result = eng.run(body.sql, cluster=body.cluster, use_cache=body.use_cache)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
    result["registered_views"] = registered
    return result


@router.get("/view-name/{fqn}", summary="Show the DuckDB view name for a table FQN")
def view_name(fqn: str):
    """Helper: returns the identifier to use in SQL after registering a table
    (``catalog.schema.table`` -> ``"catalog__schema__table"``)."""
    fqn = normalize_fqn(fqn)
    return {"table": fqn, "view_name": fqn.replace(".", "__")}
