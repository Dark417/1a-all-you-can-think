"""FastAPI application -- the Databricks functionality demo, served with Swagger UI.

Run:
    uvicorn app.main:app --reload
Then open:
    http://localhost:8000/docs      (Swagger UI -- interactive)
    http://localhost:8000/redoc     (ReDoc -- reference)
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import RedirectResponse

from .routers import (
    admin,
    autoloader,
    catalog,
    clusters,
    delta,
    dlt,
    governance,
    jobs,
    medallion,
    mlflow_router,
    notebooks,
    sql,
)

DESCRIPTION = """
A **fully local, runnable** demonstration of the Databricks **Lakehouse**,
exposed as a REST API with this interactive Swagger UI.

The storage layer is **real**: tables are genuine **Delta Lake** tables written
by **delta-rs** (no Spark/JVM) -- the same open format a Databricks cluster
reads. Compute is **DuckDB** (a Photon-style engine), and **Unity Catalog**
metadata lives in **MongoDB** (with an automatic in-memory fallback).

### Architecture mapping
| Databricks layer | Emulated locally by |
|---|---|
| Lakehouse storage (Delta Lake on S3/GCS/ADLS) | **delta-rs** -> real Delta tables on disk |
| Compute (clusters / SQL warehouses, Photon, DBUs) | **DuckDB** with per-cluster threads + DBU metering |
| Unity Catalog (3-level namespace, grants, lineage) | **MongoDB** catalog + grants + lineage edges |
| Control plane services | **FastAPI** + MongoDB |

### Suggested tour
1. `POST /clusters` — create compute (Photon, autoscaling, DBU-metered).
2. `POST /catalog/catalogs`, `/catalog/schemas` — the `catalog.schema.table` namespace.
3. `POST /delta` then append / **merge** / time-travel / **optimize** — the Delta core.
4. `POST /sql` — query Delta tables on a cluster (DuckDB `delta_scan`).
5. `POST /medallion/*` — Bronze → Silver → Gold with lineage.
6. `POST /autoloader/*` — incremental file ingestion (Auto Loader).
7. `POST /dlt/*` — declarative pipelines with data-quality expectations.
8. `POST /jobs` — multi-task Workflows (DAGs).
9. `POST /notebooks` — run SQL/Python cells on a cluster.
10. `POST /mlflow/*` — experiments, runs, model registry.
11. `GET /governance/lineage` — the Unity Catalog lineage graph.

Or just run `python demo.py` for an end-to-end scripted walkthrough.
"""

app = FastAPI(
    title="Databricks Lakehouse Functionality Demo",
    version="1.0.0",
    description=DESCRIPTION,
    contact={"name": "Databricks local demo"},
    openapi_tags=[
        {"name": "0. Admin & Health", "description": "Health, reset, architecture overview."},
        {"name": "1. Clusters (compute)", "description": "All-purpose/job clusters, autoscaling, DBU metering."},
        {"name": "2. Unity Catalog", "description": "3-level namespace, grants, effective privileges."},
        {"name": "3. Delta Lake (core)", "description": "Real Delta tables: MERGE, time travel, OPTIMIZE, VACUUM."},
        {"name": "4. Databricks SQL (DBSQL)", "description": "Run SQL on a cluster over Delta tables."},
        {"name": "5. Medallion (Bronze/Silver/Gold)", "description": "The flagship multi-hop pipeline + lineage."},
        {"name": "6. Auto Loader / Streaming", "description": "Incremental file ingestion with offsets."},
        {"name": "7. Delta Live Tables", "description": "Declarative pipelines + data-quality expectations."},
        {"name": "8. Jobs / Workflows", "description": "Multi-task DAGs, scheduling, run history."},
        {"name": "9. Notebooks", "description": "Run SQL/Python cells on a cluster."},
        {"name": "10. MLflow & Model Registry", "description": "Experiments, runs, registered models, stages."},
        {"name": "11. Governance & Lineage", "description": "Data lineage graph, audit, grants summary."},
    ],
)

for r in (
    admin,
    clusters,
    catalog,
    delta,
    sql,
    medallion,
    autoloader,
    dlt,
    jobs,
    notebooks,
    mlflow_router,
    governance,
):
    app.include_router(r.router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")
