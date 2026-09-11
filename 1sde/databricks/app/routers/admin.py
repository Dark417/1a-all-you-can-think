"""Health, catalog reset, and an architecture overview endpoint."""
from __future__ import annotations

import shutil

from fastapi import APIRouter

from ..core.catalog import get_db, reset_catalog
from ..core.config import get_settings
from ..core.engine import get_engine

router = APIRouter(prefix="/admin", tags=["0. Admin & Health"])


@router.get("/health", summary="Liveness + backend status")
def health():
    db = get_db()
    backend = "mongomock (in-memory)" if "mongomock" in type(db.client).__module__ else "mongodb"
    settings = get_settings()
    eng = get_engine()
    return {
        "status": "ok",
        "metadata_backend": backend,
        "storage_format": "delta (delta-rs, real Delta Lake tables)",
        "sql_engine": "duckdb",
        "duckdb_delta_native": eng.delta_native,
        "delta_dir": str(settings.delta_dir),
        "stage_dir": str(settings.stage_dir),
        "mlflow_tracking_uri": settings.mlflow_tracking_uri,
    }


@router.post("/reset", summary="Drop all metadata + delete all Delta tables (fresh start)")
def reset():
    """Clear the Unity Catalog metadata *and* delete the on-disk Delta tables.

    This wipes ``DELTA_DIR`` and the Auto Loader stage so the demo/tests start
    from a clean Lakehouse every time.
    """
    reset_catalog()
    settings = get_settings()
    for d in (settings.delta_dir, settings.stage_dir):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True, exist_ok=True)
    return {"status": "reset", "note": "Unity Catalog metadata + Delta storage + stage cleared."}


@router.get("/architecture", summary="The Lakehouse architecture, mapped to this demo")
def architecture():
    return {
        "paradigm": "Lakehouse = data-lake storage + warehouse-grade transactions (Delta Lake).",
        "control_plane_vs_data_plane": {
            "databricks": "Control plane (managed) holds metadata/jobs/registry; "
            "data plane (your cloud) holds Delta data + clusters.",
            "this_demo": "MongoDB = control-plane metadata; delta-rs + DuckDB = data plane.",
        },
        "layers": {
            "lakehouse_storage": {
                "databricks": "Delta tables (transaction log + Parquet) on S3/GCS/ADLS.",
                "this_demo": "REAL Delta tables on the local filesystem via delta-rs (no Spark).",
            },
            "compute": {
                "databricks": "Clusters / SQL warehouses (Photon), all-purpose vs job, autoscaling, DBUs.",
                "this_demo": "DuckDB with per-cluster thread budgets + DBU metering + autoscaling state.",
            },
            "governance": {
                "databricks": "Unity Catalog: 3-level namespace, grants, lineage, audit.",
                "this_demo": "MongoDB catalogs/schemas/tables + grants + lineage edges.",
            },
        },
        "key_principle": "Compute is ephemeral and elastic; the Delta Lakehouse is the durable "
        "single source of truth shared by every cluster, job, and pipeline.",
    }
