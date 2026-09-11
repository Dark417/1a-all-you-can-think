"""Smoke + behavior tests. Hermetic: in-memory Mongo, in-memory DuckDB, temp stage."""
from __future__ import annotations

import os
import tempfile

os.environ["USE_MONGOMOCK"] = "1"
os.environ["DUCKDB_PATH"] = ":memory:"
os.environ["STAGE_DIR"] = tempfile.mkdtemp(prefix="sf_test_stages_")

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean():
    client.post("/admin/reset")
    yield


def _bootstrap_table():
    client.post("/warehouses", json={"name": "WH", "size": "X-SMALL"})
    client.post("/databases", json={"name": "DB"})
    client.post("/databases/schemas", json={"database": "DB", "name": "S"})
    client.post(
        "/tables",
        json={
            "database": "DB", "schema": "S", "name": "T",
            "columns": [{"name": "ID", "type": "INTEGER"}, {"name": "META", "type": "VARIANT"}],
        },
    )


def test_health_uses_mongomock():
    r = client.get("/admin/health").json()
    assert r["status"] == "ok"
    assert "mongomock" in r["metadata_backend"]


def test_warehouse_lifecycle_and_credit_metering():
    client.post("/warehouses", json={"name": "WH", "size": "SMALL"})
    client.post("/sql", json={"sql": "SELECT 42", "warehouse": "WH", "use_cache": False})
    usage = client.get("/warehouses/WH/usage").json()
    assert usage["query_count"] >= 1
    assert usage["credits_used"] >= 0
    assert client.post("/warehouses/WH/suspend").json()["status"] == "suspended"
    # A query auto-resumes a suspended warehouse.
    client.post("/sql", json={"sql": "SELECT 1", "warehouse": "WH"})
    assert client.get("/warehouses/WH/usage").json()["state"] == "RUNNING"


def test_variant_insert_and_query():
    _bootstrap_table()
    client.post("/tables/DB.S.T/insert", json={"rows": [{"ID": 1, "META": {"k": "v"}}]})
    res = client.post(
        "/sql",
        json={"sql": "SELECT META->>'k' FROM \"DB$S\".\"T\"", "warehouse": "WH"},
    ).json()
    assert res["rows"][0][0] == "v"


def test_result_cache():
    client.post("/warehouses", json={"name": "WH", "size": "X-SMALL"})
    first = client.post("/sql", json={"sql": "SELECT 7 AS x", "warehouse": "WH"}).json()
    second = client.post("/sql", json={"sql": "SELECT 7 AS x", "warehouse": "WH"}).json()
    assert first["from_cache"] is False
    assert second["from_cache"] is True


def test_time_travel_and_clone():
    _bootstrap_table()
    client.post("/tables/DB.S.T/insert", json={"rows": [{"ID": 1, "META": {}}]})
    client.post("/tables/DB.S.T/insert", json={"rows": [{"ID": 2, "META": {}}]})
    hist = client.get("/time-travel/DB.S.T/history").json()
    assert len(hist["versions"]) >= 3
    v2 = client.get("/time-travel/DB.S.T/at", params={"version": 2}).json()
    assert v2["row_count"] == 1
    clone = client.post("/time-travel/clone", json={"source": "DB.S.T", "target": "DB.S.T2"})
    assert clone.json()["status"] == "cloned"


def test_streams_cdc():
    _bootstrap_table()
    client.post("/streams", json={"name": "ST", "on_table": "DB.S.T"})
    client.post("/tables/DB.S.T/insert", json={"rows": [{"ID": 99, "META": {}}]})
    changes = client.get("/streams/ST").json()
    assert changes["change_count"] == 1
    assert changes["changes"][0]["METADATA$ACTION"] == "INSERT"
    client.post("/streams/ST/consume")
    assert client.get("/streams/ST").json()["change_count"] == 0


def test_rbac_inheritance():
    client.post("/rbac/bootstrap")
    client.post("/rbac/roles", json={"name": "R1"})
    client.post("/rbac/grants", json={
        "privilege": "SELECT", "on_type": "TABLE", "on_name": "DB.S.T", "to_role": "R1"})
    client.post("/rbac/roles", json={"name": "R2"})
    client.post("/rbac/grants/role", json={"role": "R1", "to": "R2", "to_type": "ROLE"})
    eff = client.get("/rbac/roles/R2/effective-privileges").json()
    assert any(p["on_name"] == "DB.S.T" for p in eff["privileges"])


def test_python_udf():
    client.post("/warehouses", json={"name": "WH", "size": "X-SMALL"})
    client.post("/functions", json={
        "name": "dbl", "kind": "UDF_PYTHON",
        "args": [{"name": "x", "type": "INTEGER"}], "returns": "INTEGER",
        "body": "def dbl(x):\n    return x * 2"})
    out = client.post("/functions/dbl/call", params={"warehouse": "WH"}, json=[21]).json()
    assert out["result"] == 42


def test_copy_into():
    _bootstrap_table()
    client.post("/stages", json={"name": "STG"})
    client.post("/stages/file-formats", json={"name": "FF", "type": "CSV", "options": {"header": True}})
    client.put("/stages/STG/files", files={"file": ("d.csv", b"ID,META\n5,{}\n", "text/csv")})
    res = client.post("/stages/copy-into", json={
        "table": "DB.S.T", "stage": "STG", "pattern": "*.csv", "file_format": "FF"}).json()
    assert res["rows_loaded"] == 1
