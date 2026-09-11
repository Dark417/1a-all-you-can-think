"""Health, catalog reset, and an architecture summary endpoint."""
from __future__ import annotations

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
    return {
        "status": "ok",
        "metadata_backend": backend,
        "storage_engine": "duckdb",
        "duckdb_path": settings.duckdb_path,
        "stage_dir": str(settings.stage_dir),
    }


@router.post("/reset", summary="Drop all metadata + storage (fresh start)")
def reset():
    reset_catalog()
    get_engine().reset_storage()
    return {"status": "reset", "note": "All catalog metadata and DuckDB storage cleared."}


@router.get("/architecture", summary="The 3-layer architecture, mapped to this demo")
def architecture():
    return {
        "layers": {
            "cloud_services": {
                "snowflake": "Metadata, security/RBAC, optimizer, result cache, sharing.",
                "this_demo": "MongoDB catalog + FastAPI routers.",
            },
            "query_processing": {
                "snowflake": "Virtual warehouses (independent, elastic MPP compute clusters).",
                "this_demo": "DuckDB with per-warehouse thread budgets + credit metering.",
            },
            "storage": {
                "snowflake": "Centralized, immutable, columnar micro-partitions on cloud object storage.",
                "this_demo": "A DuckDB database file; Parquet row groups illustrate micro-partitions.",
            },
        },
        "key_principle": "Storage and compute scale independently; many warehouses share one copy of data.",
    }
