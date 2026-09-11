"""Behavior tests. Hermetic: in-memory Mongo, in-memory DuckDB, temp Delta dirs.

Verifies the load-bearing claims: real Delta time travel (different row counts
per version), MERGE upserts, medallion lineage, Auto Loader exactly-once, DLT
expectation quarantine, jobs DAG ordering, MLflow registry, and Unity Catalog
effective-privilege resolution.
"""
from __future__ import annotations

import os
import tempfile

# --- Hermetic setup BEFORE importing the app ---
_tmp = tempfile.mkdtemp(prefix="dbx_test_")
os.environ["USE_MONGOMOCK"] = "1"
os.environ["DUCKDB_PATH"] = ":memory:"
os.environ["DELTA_DIR"] = os.path.join(_tmp, "delta")
os.environ["STAGE_DIR"] = os.path.join(_tmp, "stage")
os.environ["MLRUNS_DIR"] = os.path.join(_tmp, "mlruns")

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean():
    client.post("/admin/reset")
    yield


def _cluster(name="wh", size="X-SMALL"):
    client.post("/clusters", json={"name": name, "size": size})


def _table(fqn="main.s.t", cols=None):
    client.post("/catalog/catalogs", json={"name": "main"})
    client.post(
        "/delta",
        json={"table": fqn, "columns": cols or [{"name": "id", "type": "INTEGER"},
                                                {"name": "name", "type": "STRING"}]},
    )


# --------------------------------------------------------------------------- #
def test_health_uses_mongomock():
    r = client.get("/admin/health").json()
    assert r["status"] == "ok"
    assert "mongomock" in r["metadata_backend"]
    assert "delta-rs" in r["storage_format"]


def test_cluster_lifecycle_and_dbu_metering():
    client.post("/clusters", json={"name": "wh", "size": "SMALL"})
    client.post("/sql", json={"sql": "SELECT 42", "cluster": "wh", "use_cache": False})
    usage = client.get("/clusters/wh/usage").json()
    assert usage["query_count"] >= 1
    assert usage["dbus_used"] > 0
    assert client.post("/clusters/wh/terminate").json()["status"] == "terminated"
    # A query auto-starts a terminated cluster.
    client.post("/sql", json={"sql": "SELECT 1", "cluster": "wh", "use_cache": False})
    assert client.get("/clusters/wh/usage").json()["state"] == "RUNNING"


def test_cluster_resize_autoscaling():
    client.post("/clusters", json={"name": "wh", "size": "SMALL", "min_workers": 1, "max_workers": 4})
    r = client.post("/clusters/wh/resize", json={"size": "LARGE", "current_workers": 3}).json()
    assert r["size"] == "LARGE"
    assert client.get("/clusters/wh/usage").json()["current_workers"] == 3


def test_delta_append_merge_timetravel_history():
    _cluster()
    _table()
    client.post("/delta/main.s.t/append", json={"rows": [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]})
    # MERGE: update id=2, insert id=3.
    client.post("/delta/main.s.t/merge",
                json={"rows": [{"id": 2, "name": "B"}, {"id": 3, "name": "c"}], "key_columns": ["id"]})
    latest = client.get("/delta/main.s.t/data").json()
    assert latest["row_count"] == 3
    names = {r[1] for r in latest["rows"]}
    assert "B" in names and "c" in names  # merge updated + inserted

    # Time travel: version 1 (after the append) had only 2 rows.
    v1 = client.get("/delta/main.s.t/data", params={"version": 1}).json()
    assert v1["row_count"] == 2
    assert v1["row_count"] != latest["row_count"]

    hist = client.get("/delta/main.s.t/history").json()["history"]
    ops = {h.get("operation") for h in hist}
    assert "MERGE" in ops


def test_delta_schema_evolution():
    _table("main.s.evo", cols=[{"name": "id", "type": "INTEGER"}])
    client.post("/delta/main.s.evo/append", json={"rows": [{"id": 1}]})
    r = client.post("/delta/main.s.evo/append",
                    json={"rows": [{"id": 2, "extra": "x"}], "evolve_schema": True}).json()
    assert r["schema_evolved"] is True
    detail = client.get("/delta/main.s.evo/describe-detail").json()
    assert any(c["name"] == "extra" for c in detail["schema"])


def test_delta_optimize_and_vacuum():
    _table("main.s.opt")
    client.post("/delta/main.s.opt/append", json={"rows": [{"id": 1, "name": "a"}]})
    client.post("/delta/main.s.opt/append", json={"rows": [{"id": 2, "name": "b"}]})
    assert client.post("/delta/main.s.opt/optimize").json()["status"] == "optimized"
    vac = client.post("/delta/main.s.opt/vacuum", params={"dry_run": True}).json()
    assert vac["dry_run"] is True


def test_sql_result_cache():
    _cluster()
    _table()
    client.post("/delta/main.s.t/append", json={"rows": [{"id": 1, "name": "a"}]})
    q = {"sql": "SELECT COUNT(*) FROM main__s__t", "cluster": "wh",
         "register": ["main.s.t"]}
    first = client.post("/sql", json=q).json()
    second = client.post("/sql", json=q).json()
    assert first["from_cache"] is False
    assert second["from_cache"] is True
    assert first["rows"][0][0] == 1


def test_catalog_grants_effective_privileges():
    _table()
    client.post("/catalog/grants", json={
        "privilege": "SELECT", "securable_type": "TABLE",
        "securable_name": "main.s.t", "principal": "eng"})
    eff = client.get("/catalog/effective-privileges",
                     params={"table": "main.s.t", "principal": "eng"}).json()
    assert eff["can_select"] is True
    # A principal with no grant cannot select.
    eff2 = client.get("/catalog/effective-privileges",
                      params={"table": "main.s.t", "principal": "nobody"}).json()
    assert eff2["can_select"] is False


def test_medallion_lineage():
    client.post("/medallion/bronze", json={
        "table": "main.m.bronze",
        "rows": [{"event_id": 1, "type": "a"}, {"event_id": 1, "type": "a"},
                 {"event_id": 2, "type": "b"}, {"event_id": 3, "type": None}]})
    s = client.post("/medallion/silver", json={
        "source": "main.m.bronze", "target": "main.m.silver",
        "dedupe_key": "event_id", "drop_nulls_in": ["type"]}).json()
    # 4 rows -> drop 1 dup + 1 null = 2 rows.
    assert s["rows_out"] == 2
    client.post("/medallion/gold", json={
        "source": "main.m.silver", "target": "main.m.gold", "group_by": ["type"]})
    up = client.get("/governance/lineage/main.m.gold/upstream").json()["upstream"]
    assert "main.m.bronze" in up and "main.m.silver" in up


def test_autoloader_incremental_exactly_once():
    client.post("/autoloader", json={
        "name": "ld", "source_dir": "in", "format": "json", "target": "main.b.raw"})
    client.put("/autoloader/ld/files",
               files={"file": ("b1.json", b'{"id": 1}\n{"id": 2}\n', "application/json")})
    r1 = client.post("/autoloader/ld/trigger", json={"trigger_once": True}).json()
    assert r1["rows_loaded"] == 2
    # Re-trigger with no new files -> nothing loaded.
    r2 = client.post("/autoloader/ld/trigger", json={"trigger_once": True}).json()
    assert r2["files_processed"] == 0 and r2["rows_loaded"] == 0
    # New file -> only it is ingested.
    client.put("/autoloader/ld/files",
               files={"file": ("b2.json", b'{"id": 3}\n', "application/json")})
    r3 = client.post("/autoloader/ld/trigger", json={"trigger_once": True}).json()
    assert r3["rows_loaded"] == 1
    assert client.get("/autoloader/ld").json()["checkpoint_offset"]["processed_file_count"] == 2


def test_dlt_expectation_quarantine():
    client.post("/dlt", json={
        "name": "p", "target_catalog": "main", "target_schema": "dlt",
        "steps": [
            {"name": "raw", "query": "SELECT * FROM (VALUES (1, 10.0), (2, -1.0), (3, 5.0)) AS t(id, amount)",
             "depends_on": [], "expectations": []},
            {"name": "clean", "query": "SELECT * FROM raw", "depends_on": ["raw"],
             "expectations": [{"name": "pos", "constraint": "amount > 0", "action": "DROP"}]},
        ]})
    report = client.post("/dlt/p/run", json={}).json()["report"]
    clean = next(r for r in report if r["step"] == "clean")
    assert clean["rows_in"] == 3
    assert clean["rows_written"] == 2  # the negative-amount row is quarantined
    exp = clean["expectations"][0]
    assert exp["failed"] == 1 and exp["quarantined"] == 1


def test_dlt_expectation_fail_aborts():
    client.post("/dlt", json={
        "name": "pf", "target_catalog": "main", "target_schema": "dlt",
        "steps": [
            {"name": "raw", "query": "SELECT * FROM (VALUES (1, -1.0)) AS t(id, amount)",
             "depends_on": [],
             "expectations": [{"name": "pos", "constraint": "amount > 0", "action": "FAIL"}]},
        ]})
    r = client.post("/dlt/pf/run", json={})
    assert r.status_code == 422


def test_jobs_dag_run():
    _cluster("wh")
    client.post("/jobs", json={
        "name": "j", "cluster": "wh",
        "tasks": [
            {"key": "t1", "sql": "SELECT 1", "depends_on": []},
            {"key": "t2", "sql": "SELECT 2", "depends_on": ["t1"]},
            {"key": "t3", "sql": "SELECT 3", "depends_on": ["t1", "t2"]},
        ]})
    run = client.post("/jobs/j/run").json()
    assert run["state"] == "SUCCEEDED"
    order = run["run_order"]
    assert order.index("t1") < order.index("t2") < order.index("t3")
    assert all(t["state"] == "SUCCEEDED" for t in run["tasks"])


def test_notebook_sql_and_python_cells():
    _cluster("wh")
    client.post("/notebooks", json={
        "name": "nb",
        "cells": [
            {"language": "sql", "source": "SELECT 6 * 7 AS answer"},
            {"language": "python", "source": "result = 1 + 2 + 3"},
        ]})
    out = client.post("/notebooks/nb/run", json={"cluster": "wh"}).json()["outputs"]
    assert out[0]["rows"][0][0] == 42
    assert out[1]["result"] == 6


def test_mlflow_experiment_run_registry():
    client.post("/mlflow/experiments", json={"name": "exp"})
    run = client.post("/mlflow/runs", json={
        "experiment": "exp", "run_name": "r1",
        "params": {"a": 1}, "metrics": {"rmse": 0.1}, "register_as": "mymodel"}).json()
    assert run["registered_model"]["version"] == 1
    runs = client.get("/mlflow/runs", params={"experiment": "exp"}).json()
    assert runs["run_count"] == 1
    models = client.get("/mlflow/models").json()["registered_models"]
    assert any(m["name"] == "mymodel" for m in models)
    t = client.post("/mlflow/models/transition",
                    json={"model": "mymodel", "version": 1, "stage": "Production"}).json()
    assert t["stage"] == "Production"
