"""FastAPI application -- the Snowflake functionality demo, served with Swagger UI.

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
    databases,
    functions,
    governance,
    rbac,
    sql,
    stages,
    streams,
    tables,
    tasks,
    timetravel,
    warehouses,
)

DESCRIPTION = """
A **fully local, runnable** demonstration of Snowflake's core functionality,
exposed as a REST API with this interactive Swagger UI.

### Architecture mapping
| Snowflake layer | Emulated locally by |
|---|---|
| Cloud Services (metadata, RBAC, optimizer, cache) | **MongoDB** catalog + FastAPI |
| Virtual Warehouses (elastic compute) | **DuckDB** with per-warehouse thread budgets + credit metering |
| Storage (immutable columnar micro-partitions) | A **DuckDB** file; Parquet row groups show micro-partitions |

### Suggested tour
1. `POST /warehouses` — create compute.
2. `POST /databases`, `POST /databases/schemas`, `POST /tables` — build a namespace.
3. `POST /tables/{fqn}/insert` then `GET /tables/{fqn}/data` — load & query.
4. `GET /tables/{fqn}/micro-partitions` — see columnar pruning metadata.
5. `POST /stages`, upload a file, `POST /stages/copy-into` — bulk ingest.
6. `POST /streams` + `POST /tasks` — CDC and scheduled pipelines.
7. `GET /time-travel/{fqn}/history`, `POST /time-travel/clone` — time travel & zero-copy clone.
8. `POST /rbac/*` — roles, grants, inheritance.

Or just run `python demo.py` for an end-to-end scripted walkthrough.
"""

app = FastAPI(
    title="Snowflake Functionality Demo",
    version="1.0.0",
    description=DESCRIPTION,
    contact={"name": "Snowflake local demo"},
    openapi_tags=[
        {"name": "0. Admin & Health", "description": "Health, reset, architecture overview."},
        {"name": "1. Warehouses (compute)", "description": "Elastic compute, suspend/resume/resize, credit metering."},
        {"name": "2. Databases & Schemas", "description": "The DATABASE.SCHEMA namespace."},
        {"name": "3. Tables & Semi-structured data", "description": "Structured + VARIANT, micro-partitions."},
        {"name": "4. SQL execution", "description": "Run arbitrary SQL on a warehouse."},
        {"name": "5. Stages, COPY INTO & Snowpipe", "description": "Bulk + continuous ingestion."},
        {"name": "6. Streams (CDC)", "description": "Change data capture via version diffs."},
        {"name": "7. Tasks (scheduled DAGs)", "description": "Scheduled SQL and task graphs."},
        {"name": "8. Time Travel & Cloning", "description": "Query the past; zero-copy clones."},
        {"name": "9. RBAC (roles, users, grants)", "description": "Role hierarchy and privilege checks."},
        {"name": "10. UDFs & Stored Procedures", "description": "Extend SQL with SQL/Python."},
        {"name": "11. Sharing, Monitors & History", "description": "Governance & observability."},
    ],
)

for r in (
    admin,
    warehouses,
    databases,
    tables,
    sql,
    stages,
    streams,
    tasks,
    timetravel,
    rbac,
    functions,
    governance,
):
    app.include_router(r.router)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/docs")
