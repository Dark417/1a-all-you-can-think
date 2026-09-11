"""End-to-end scripted walkthrough of every Snowflake feature in this demo.

Runs entirely in-process via FastAPI's TestClient -- no server, no MongoDB, no
cloud account required. Forces the in-memory catalog so it is hermetic.

    python demo.py
"""
from __future__ import annotations

import json
import os
import tempfile

os.environ.setdefault("USE_MONGOMOCK", "1")
os.environ.setdefault("DUCKDB_PATH", ":memory:")
# Hermetic, throwaway storage so the demo is fully repeatable.
os.environ.setdefault("STAGE_DIR", tempfile.mkdtemp(prefix="sf_demo_stages_"))

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
    print(" SNOWFLAKE FUNCTIONALITY DEMO — end-to-end")
    print("=" * 78)

    call("GET", "/admin/health", "Health check (shows metadata backend = mongomock)")
    call("POST", "/admin/reset", "Start from a clean catalog")

    # 1. Compute ---------------------------------------------------------------
    call("POST", "/warehouses", "CREATE WAREHOUSE COMPUTE_WH (X-SMALL)",
         json={"name": "COMPUTE_WH", "size": "X-SMALL"})
    call("POST", "/warehouses/COMPUTE_WH/resize", "Scale up to MEDIUM (no data move)",
         json={"size": "MEDIUM"})

    # 2. Namespace -------------------------------------------------------------
    call("POST", "/databases", "CREATE DATABASE ANALYTICS", json={"name": "ANALYTICS"})
    call("POST", "/databases/schemas", "CREATE SCHEMA ANALYTICS.SALES",
         json={"database": "ANALYTICS", "name": "SALES"})

    # 3. Tables + semi-structured ---------------------------------------------
    call("POST", "/tables", "CREATE TABLE with a VARIANT column",
         json={"database": "ANALYTICS", "schema": "SALES", "name": "CUSTOMERS",
               "columns": [{"name": "ID", "type": "INTEGER"},
                           {"name": "NAME", "type": "VARCHAR"},
                           {"name": "PROFILE", "type": "VARIANT"}]})
    call("POST", "/tables/ANALYTICS.SALES.CUSTOMERS/insert", "INSERT nested JSON into VARIANT",
         json={"rows": [
             {"ID": 1, "NAME": "Ada", "PROFILE": {"tier": "gold", "tags": ["vip"]}},
             {"ID": 2, "NAME": "Linus", "PROFILE": {"tier": "silver"}}]})
    call("GET", "/tables/ANALYTICS.SALES.CUSTOMERS/data", "SELECT * preview")
    call("POST", "/sql", "Query VARIANT path with SQL on the warehouse",
         json={"sql": "SELECT NAME, PROFILE->>'tier' AS tier "
                      "FROM \"ANALYTICS$SALES\".\"CUSTOMERS\" ORDER BY ID",
               "warehouse": "COMPUTE_WH"})
    call("GET", "/tables/ANALYTICS.SALES.CUSTOMERS/micro-partitions",
         "Inspect columnar micro-partition (row-group) stats")

    # 4. Bulk ingestion --------------------------------------------------------
    call("POST", "/stages", "CREATE STAGE RAW", json={"name": "RAW"})
    call("POST", "/stages/file-formats", "CREATE FILE FORMAT MY_CSV",
         json={"name": "MY_CSV", "type": "CSV", "options": {"header": True}})
    csv = b"ID,NAME,PROFILE\n3,Grace,{}\n4,Dennis,{}\n"
    call("PUT", "/stages/RAW/files", "PUT customers.csv @RAW",
         files={"file": ("customers.csv", csv, "text/csv")})
    call("POST", "/stages/copy-into", "COPY INTO CUSTOMERS FROM @RAW",
         json={"table": "ANALYTICS.SALES.CUSTOMERS", "stage": "RAW",
               "pattern": "*.csv", "file_format": "MY_CSV", "warehouse": "COMPUTE_WH"})

    # 5. Snowpipe (auto-ingest) -----------------------------------------------
    call("POST", "/stages/pipes", "CREATE PIPE auto-ingesting @RAW",
         json={"name": "CUST_PIPE", "auto_ingest": True,
               "copy_statement": {"table": "ANALYTICS.SALES.CUSTOMERS", "stage": "RAW",
                                  "pattern": "auto_*.csv", "file_format": "MY_CSV"}})
    call("PUT", "/stages/RAW/files", "Drop auto_1.csv -> pipe ingests automatically",
         files={"file": ("auto_1.csv", b"ID,NAME,PROFILE\n5,Ken,{}\n", "text/csv")})
    call("GET", "/stages/pipes", "SHOW PIPES (files_loaded should be > 0)")

    # 6. Streams (CDC) ---------------------------------------------------------
    call("POST", "/streams", "CREATE STREAM on CUSTOMERS",
         json={"name": "CUST_STREAM", "on_table": "ANALYTICS.SALES.CUSTOMERS"})
    call("POST", "/tables/ANALYTICS.SALES.CUSTOMERS/insert", "INSERT a new row",
         json={"rows": [{"ID": 6, "NAME": "Margaret", "PROFILE": {"tier": "gold"}}]})
    call("GET", "/streams/CUST_STREAM", "Read pending CDC changes from the stream")
    call("POST", "/streams/CUST_STREAM/consume", "Advance the stream offset")

    # 7. Tasks (DAG) -----------------------------------------------------------
    call("POST", "/tables", "CREATE TABLE GOLD.CUSTOMER_COUNT",
         json={"database": "ANALYTICS", "schema": "SALES", "name": "CUSTOMER_COUNT",
               "columns": [{"name": "N", "type": "INTEGER"}]})
    call("POST", "/tasks", "CREATE root TASK (refresh aggregate)",
         json={"name": "REFRESH_COUNT", "warehouse": "COMPUTE_WH",
               "sql": "INSERT INTO \"ANALYTICS$SALES\".\"CUSTOMER_COUNT\" "
                      "SELECT COUNT(*) FROM \"ANALYTICS$SALES\".\"CUSTOMERS\""})
    call("POST", "/tasks/REFRESH_COUNT/run", "Run the task now")
    call("GET", "/tasks/REFRESH_COUNT/history", "Task run history")

    # 8. Time travel + clone ---------------------------------------------------
    call("GET", "/time-travel/ANALYTICS.SALES.CUSTOMERS/history", "Version history")
    call("GET", "/time-travel/ANALYTICS.SALES.CUSTOMERS/at?version=1",
         "Query the table AS OF version 1")
    call("POST", "/time-travel/clone",
         "Zero-copy CLONE CUSTOMERS -> CUSTOMERS_BACKUP",
         json={"source": "ANALYTICS.SALES.CUSTOMERS", "target": "ANALYTICS.SALES.CUSTOMERS_BACKUP"})

    # 9. RBAC ------------------------------------------------------------------
    call("POST", "/rbac/bootstrap", "Create system roles")
    call("POST", "/rbac/roles", "CREATE ROLE DATA_ENGINEER", json={"name": "DATA_ENGINEER"})
    call("POST", "/rbac/grants", "GRANT SELECT ON CUSTOMERS TO DATA_ENGINEER",
         json={"privilege": "SELECT", "on_type": "TABLE",
               "on_name": "ANALYTICS.SALES.CUSTOMERS", "to_role": "DATA_ENGINEER"})
    call("GET", "/rbac/check?role=DATA_ENGINEER&privilege=SELECT&on_name=ANALYTICS.SALES.CUSTOMERS",
         "Authorization check -> allowed = true")

    # 10. UDFs -----------------------------------------------------------------
    call("POST", "/functions", "CREATE PYTHON UDF tax(amount)",
         json={"name": "tax", "kind": "UDF_PYTHON",
               "args": [{"name": "amount", "type": "DOUBLE"}], "returns": "DOUBLE",
               "body": "def tax(amount):\n    return round(amount * 0.2, 2)"})
    call("POST", "/functions/tax/call", "Call tax(100.0)", json=[100.0])

    # 11. Governance -----------------------------------------------------------
    call("POST", "/governance/shares", "CREATE SHARE exposing CUSTOMERS",
         json={"name": "CUST_SHARE", "objects": ["ANALYTICS.SALES.CUSTOMERS"],
               "accounts": ["PARTNER_ACCT"]})
    call("POST", "/governance/resource-monitors", "CREATE RESOURCE MONITOR (1 credit quota)",
         json={"name": "MON", "credit_quota": 1.0, "on_breach": "SUSPEND",
               "warehouses": ["COMPUTE_WH"]})
    call("GET", "/governance/resource-monitors/evaluate", "Evaluate credit quota")
    call("GET", "/warehouses/COMPUTE_WH/usage", "Credits consumed by COMPUTE_WH")
    call("GET", "/governance/query-history?limit=5", "Recent QUERY_HISTORY")

    print("\n" + "=" * 78)
    print(" DEMO COMPLETE — every feature exercised successfully.")
    print(" Start the API for interactive use:  uvicorn app.main:app --reload")
    print(" Then open Swagger UI at:            http://localhost:8000/docs")
    print("=" * 78)


if __name__ == "__main__":
    main()
