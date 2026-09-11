"""End-to-end scripted walkthrough of every Databricks feature in this demo.

Runs entirely in-process via FastAPI's TestClient -- no server, no MongoDB, no
Spark, no cloud account. Forces the in-memory catalog and throwaway temp dirs so
it is fully hermetic and repeatable.

    python demo.py
"""
from __future__ import annotations

import json
import os
import tempfile

# --- Hermetic setup: do this BEFORE importing the app ---------------------- #
os.environ.setdefault("USE_MONGOMOCK", "1")
os.environ.setdefault("DUCKDB_PATH", ":memory:")
_tmp = tempfile.mkdtemp(prefix="dbx_demo_")
os.environ.setdefault("DELTA_DIR", os.path.join(_tmp, "delta"))
os.environ.setdefault("STAGE_DIR", os.path.join(_tmp, "stage"))
os.environ.setdefault("MLRUNS_DIR", os.path.join(_tmp, "mlruns"))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)
STEP = 0


def call(method: str, path: str, label: str, **kw):
    global STEP
    STEP += 1
    resp = client.request(method, path, **kw)
    ok = resp.status_code < 400
    mark = "OK " if ok else "ERR"
    print(f"\n[{STEP:02d}] {mark} {method:6} {path}\n     {label}")
    try:
        body = resp.json()
        snippet = json.dumps(body, default=str)
        print("     ->", snippet[:300] + ("..." if len(snippet) > 300 else ""))
    except Exception:
        print("     ->", resp.text[:200])
    assert ok, f"Step failed: {label} -> {resp.status_code} {resp.text}"
    return resp.json() if ok else None


def main() -> None:
    print("=" * 78)
    print(" DATABRICKS LAKEHOUSE FUNCTIONALITY DEMO — end-to-end")
    print("=" * 78)

    call("GET", "/admin/health", "Health (metadata=mongomock, storage=real delta-rs)")
    call("POST", "/admin/reset", "Start from a clean Lakehouse + metastore")
    call("GET", "/admin/architecture", "Lakehouse architecture overview")

    # 1. Clusters (compute) ----------------------------------------------------
    call("POST", "/clusters", "Create an all-purpose Photon cluster (autoscaling)",
         json={"name": "analytics-cluster", "size": "SMALL", "min_workers": 1, "max_workers": 4})
    call("POST", "/clusters/analytics-cluster/resize", "Scale up to MEDIUM, 2 workers",
         json={"size": "MEDIUM", "current_workers": 2})

    # 2. Unity Catalog ---------------------------------------------------------
    call("POST", "/catalog/catalogs", "CREATE CATALOG main", json={"name": "main"})
    call("POST", "/catalog/schemas", "CREATE SCHEMA main.sales",
         json={"catalog": "main", "name": "sales"})

    # 3. Delta Lake (the core) -------------------------------------------------
    call("POST", "/delta", "CREATE Delta TABLE main.sales.customers",
         json={"table": "main.sales.customers",
               "columns": [{"name": "id", "type": "INTEGER"},
                           {"name": "name", "type": "STRING"},
                           {"name": "tier", "type": "STRING"}]})
    call("POST", "/delta/main.sales.customers/append", "Append 3 rows (Delta commit v1)",
         json={"rows": [{"id": 1, "name": "Ada", "tier": "gold"},
                        {"id": 2, "name": "Linus", "tier": "silver"},
                        {"id": 3, "name": "Grace", "tier": "gold"}]})
    call("POST", "/delta/main.sales.customers/merge", "MERGE (upsert): update id=2, insert id=4",
         json={"rows": [{"id": 2, "name": "Linus", "tier": "gold"},
                        {"id": 4, "name": "Dennis", "tier": "bronze"}],
               "key_columns": ["id"]})
    call("POST", "/delta/main.sales.customers/update", "UPDATE tier WHERE id=1",
         json={"set": {"tier": "'platinum'"}, "predicate": "id = 1"})
    call("POST", "/delta/main.sales.customers/delete", "DELETE WHERE id=3",
         json={"predicate": "id = 3"})
    call("POST", "/delta/main.sales.customers/append", "Schema evolution: append with new column",
         json={"rows": [{"id": 5, "name": "Ken", "tier": "gold", "country": "US"}],
               "evolve_schema": True})
    hist = call("GET", "/delta/main.sales.customers/history", "Transaction-log history (time travel)")
    call("GET", "/delta/main.sales.customers/data?version=1",
         "TIME TRAVEL: read version 1 (before merge/update/delete)")
    call("GET", "/delta/main.sales.customers/data", "Read latest version")
    call("POST", "/delta/main.sales.customers/optimize", "OPTIMIZE (compact small files)")
    call("POST", "/delta/main.sales.customers/zorder", "Z-ORDER BY (id)", json={"columns": ["id"]})
    call("POST", "/delta/main.sales.customers/vacuum?retention_hours=168&dry_run=true",
         "VACUUM (dry-run: list removable files)")
    call("GET", "/delta/main.sales.customers/describe-detail",
         "DESCRIBE DETAIL (version, num files, size)")

    # 4. Databricks SQL --------------------------------------------------------
    call("POST", "/sql", "Run SQL on the cluster over the Delta table (delta_scan)",
         json={"sql": "SELECT tier, COUNT(*) AS n FROM main__sales__customers GROUP BY tier ORDER BY tier",
               "cluster": "analytics-cluster",
               "register": ["main.sales.customers"]})
    call("POST", "/sql", "Re-run identical query -> served from result cache",
         json={"sql": "SELECT tier, COUNT(*) AS n FROM main__sales__customers GROUP BY tier ORDER BY tier",
               "cluster": "analytics-cluster",
               "register": ["main.sales.customers"]})

    # 2b. Unity Catalog grants -------------------------------------------------
    call("GET", "/catalog/tables/main.sales.customers/describe", "DESCRIBE TABLE (metadata + Delta detail)")
    call("POST", "/catalog/grants", "GRANT SELECT ON main.sales.customers TO data_engineers",
         json={"privilege": "SELECT", "securable_type": "TABLE",
               "securable_name": "main.sales.customers", "principal": "data_engineers"})
    call("POST", "/catalog/grants", "GRANT USE_SCHEMA ON main.sales TO data_engineers",
         json={"privilege": "USE_SCHEMA", "securable_type": "SCHEMA",
               "securable_name": "main.sales", "principal": "data_engineers"})
    call("GET", "/catalog/effective-privileges?table=main.sales.customers&principal=data_engineers",
         "Resolve effective privileges (can_select=true)")

    # 5. Medallion -------------------------------------------------------------
    call("POST", "/medallion/bronze", "Bronze: land raw events",
         json={"table": "main.medallion.bronze_events",
               "rows": [{"event_id": 1, "event_type": "click", "user": "a"},
                        {"event_id": 1, "event_type": "click", "user": "a"},
                        {"event_id": 2, "event_type": "view", "user": "b"},
                        {"event_id": 3, "event_type": None, "user": "c"}]})
    call("POST", "/medallion/silver", "Silver: dedupe + drop null event_type",
         json={"source": "main.medallion.bronze_events", "target": "main.medallion.silver_events",
               "dedupe_key": "event_id", "drop_nulls_in": ["event_type"]})
    call("POST", "/medallion/gold", "Gold: aggregate counts by event_type",
         json={"source": "main.medallion.silver_events", "target": "main.medallion.gold_event_counts",
               "group_by": ["event_type"]})

    # 6. Auto Loader -----------------------------------------------------------
    call("POST", "/autoloader", "Create Auto Loader stream watching a landing dir",
         json={"name": "events_loader", "source_dir": "incoming", "format": "json",
               "target": "main.bronze.raw_events"})
    call("PUT", "/autoloader/events_loader/files", "Land batch1.json",
         files={"file": ("batch1.json", b'{"id": 1, "v": "x"}\n{"id": 2, "v": "y"}\n', "application/json")})
    call("POST", "/autoloader/events_loader/trigger", "Trigger-once micro-batch (2 new rows)",
         json={"trigger_once": True})
    call("POST", "/autoloader/events_loader/trigger", "Trigger again -> 0 new files (exactly-once)",
         json={"trigger_once": True})
    call("PUT", "/autoloader/events_loader/files", "Land batch2.json",
         files={"file": ("batch2.json", b'{"id": 3, "v": "z"}\n', "application/json")})
    call("POST", "/autoloader/events_loader/trigger", "Trigger -> ingests only batch2",
         json={"trigger_once": True})
    call("GET", "/autoloader/events_loader", "Show checkpoint offset (3 processed files)")

    # 7. Delta Live Tables -----------------------------------------------------
    call("POST", "/dlt", "Define a DLT pipeline with expectations",
         json={"name": "sales_pipeline", "target_catalog": "main", "target_schema": "dlt",
               "steps": [
                   {"name": "raw_orders",
                    "query": "SELECT * FROM (VALUES (1, 100.0), (2, -5.0), (3, 50.0)) AS t(order_id, amount)",
                    "depends_on": [], "expectations": []},
                   {"name": "clean_orders",
                    "query": "SELECT * FROM raw_orders",
                    "depends_on": ["raw_orders"],
                    "expectations": [{"name": "positive_amount", "constraint": "amount > 0", "action": "DROP"}]},
               ]})
    call("POST", "/dlt/sales_pipeline/run", "Run pipeline DAG (quarantine amount<=0)", json={})

    # 8. Jobs / Workflows ------------------------------------------------------
    call("POST", "/jobs", "Create a multi-task job (DAG)",
         json={"name": "nightly_etl", "cluster": "analytics-cluster",
               "tasks": [
                   {"key": "t1", "sql": "SELECT 1", "depends_on": []},
                   {"key": "t2", "sql": "SELECT 2", "depends_on": ["t1"]},
                   {"key": "t3", "sql": "SELECT 3", "depends_on": ["t1"]},
               ]})
    call("POST", "/jobs/nightly_etl/run", "Run the job now (executes t1 -> t2,t3)")
    call("GET", "/jobs/nightly_etl/runs", "Job run history (per-task status)")

    # 9. Notebooks -------------------------------------------------------------
    call("POST", "/notebooks", "Register a notebook (SQL + Python cells)",
         json={"name": "explore",
               "cells": [
                   {"language": "sql", "source": "SELECT 6 * 7 AS answer"},
                   {"language": "python", "source": "result = sum(range(10))\nprint('computed', result)"},
               ]})
    call("POST", "/notebooks/explore/run", "Execute the notebook on the cluster",
         json={"cluster": "analytics-cluster"})

    # 10. MLflow ---------------------------------------------------------------
    call("POST", "/mlflow/experiments", "Create experiment 'churn-model'", json={"name": "churn-model"})
    run = call("POST", "/mlflow/runs", "Log a run (params/metrics) + register a model",
               json={"experiment": "churn-model", "run_name": "baseline",
                     "params": {"alpha": 0.5}, "metrics": {"rmse": 0.12},
                     "tags": {"team": "ml"}, "register_as": "churn-model"})
    call("GET", "/mlflow/runs?experiment=churn-model", "List runs")
    call("GET", "/mlflow/models", "List registered models + versions")
    version = run["registered_model"]["version"]
    call("POST", "/mlflow/models/transition", "Promote model version to Staging",
         json={"model": "churn-model", "version": version, "stage": "Staging"})

    # 11. Governance & Lineage -------------------------------------------------
    call("GET", "/governance/lineage", "Unity Catalog data lineage graph")
    call("GET", "/governance/lineage/main.medallion.gold_event_counts/upstream",
         "Upstream sources of the gold table")
    call("GET", "/governance/grants-summary", "Grants summary by principal")
    call("GET", "/governance/query-history?limit=5", "Audit: recent query history")
    call("GET", "/clusters/analytics-cluster/usage", "DBUs consumed by the cluster")

    print("\n" + "=" * 78)
    print(f" DEMO COMPLETE — {STEP} steps, every feature exercised successfully.")
    print(" Start the API for interactive use:  uvicorn app.main:app --reload")
    print(" Then open Swagger UI at:            http://localhost:8000/docs")
    print("=" * 78)


if __name__ == "__main__":
    main()
