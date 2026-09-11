"""Delta Lake -- the core of the Lakehouse.

Every operation here uses **real delta-rs** against a genuine Delta table on
disk (``_delta_log`` + Parquet). So ACID commits, MERGE upserts, UPDATE/DELETE,
time travel, schema evolution, OPTIMIZE/Z-ORDER and VACUUM all truly work -- the
resulting table is byte-for-byte the open format a Databricks cluster reads.

Endpoints:
  * create / append / merge (upsert) / update / delete
  * time travel: read a past version, list history
  * schema evolution: append with new columns
  * OPTIMIZE (compaction), Z-ORDER, VACUUM (dry run)
  * DESCRIBE DETAIL (version, num files, size)
"""
from __future__ import annotations

import pyarrow as pa
from fastapi import APIRouter, HTTPException, Query

from ..core import delta_io
from ..core.catalog import Collections, get_db
from ..core.metastore import register_table
from ..core.naming import delta_path, normalize_fqn
from ..models import (
    DeltaCreate,
    DeltaDelete,
    DeltaMerge,
    DeltaUpdate,
    DeltaWrite,
    ZOrderRequest,
)

router = APIRouter(prefix="/delta", tags=["3. Delta Lake (core)"])

# Map declared column types -> Arrow types for the initial (empty) table schema.
_ARROW_TYPES = {
    "INT": pa.int64(),
    "INTEGER": pa.int64(),
    "BIGINT": pa.int64(),
    "LONG": pa.int64(),
    "DOUBLE": pa.float64(),
    "FLOAT": pa.float64(),
    "STRING": pa.string(),
    "VARCHAR": pa.string(),
    "TEXT": pa.string(),
    "BOOLEAN": pa.bool_(),
    "BOOL": pa.bool_(),
    "TIMESTAMP": pa.timestamp("us"),
    "DATE": pa.date32(),
}


def _arrow_schema(columns) -> pa.Schema:
    return pa.schema(
        [(c.name, _ARROW_TYPES.get(c.type.upper(), pa.string())) for c in columns]
    )


@router.post("", summary="CREATE TABLE (empty Delta table, registered in Unity Catalog)")
def create_table(body: DeltaCreate):
    fqn = normalize_fqn(body.table)
    if delta_io.table_exists(fqn):
        raise HTTPException(409, f"Delta table '{fqn}' already exists.")
    schema = _arrow_schema(body.columns)
    # Write an empty table so version 0 establishes the schema (and _delta_log).
    delta_io.create_or_overwrite(
        fqn, pa.table({c.name: [] for c in body.columns}, schema=schema),
        partition_by=body.partition_by or None,
    )
    register_table(fqn, columns=[c.model_dump() for c in body.columns])
    return {"status": "created", "table": fqn, "version": 0, "location": delta_path(fqn)}


@router.post("/{fqn}/append", summary="Append rows (optionally evolving the schema)")
def append_rows(fqn: str, body: DeltaWrite):
    fqn = _require(fqn)
    schema = None if body.evolve_schema else _existing_schema(fqn)
    data = delta_io.rows_to_arrow(body.rows, schema=schema)
    delta_io.append(fqn, data, evolve_schema=body.evolve_schema)
    dt = delta_io.open_table(fqn)
    return {
        "status": "appended",
        "rows": len(body.rows),
        "version": dt.version(),
        "schema_evolved": body.evolve_schema,
    }


@router.post("/{fqn}/merge", summary="MERGE INTO (upsert) -- update matches, insert the rest")
def merge(fqn: str, body: DeltaMerge):
    fqn = _require(fqn)
    source = delta_io.rows_to_arrow(body.rows)
    metrics = delta_io.merge_upsert(fqn, source, body.key_columns)
    return {"status": "merged", "version": delta_io.open_table(fqn).version(), "metrics": metrics}


@router.post("/{fqn}/update", summary="UPDATE ... SET col = <expr> WHERE <predicate>")
def update_rows(fqn: str, body: DeltaUpdate):
    fqn = _require(fqn)
    metrics = delta_io.update(fqn, body.set, body.predicate)
    return {"status": "updated", "version": delta_io.open_table(fqn).version(), "metrics": metrics}


@router.post("/{fqn}/delete", summary="DELETE FROM ... WHERE <predicate>")
def delete_rows(fqn: str, body: DeltaDelete):
    fqn = _require(fqn)
    metrics = delta_io.delete(fqn, body.predicate)
    return {"status": "deleted", "version": delta_io.open_table(fqn).version(), "metrics": metrics}


@router.get("/{fqn}/data", summary="Read the table (latest, or a past version via ?version=)")
def read(fqn: str, version: int | None = Query(None), limit: int = 100):
    fqn = _require(fqn)
    return delta_io.read_rows(fqn, version=version, limit=limit)


@router.get("/{fqn}/history", summary="Delta transaction-log history (time travel)")
def history(fqn: str):
    """Every commit in ``_delta_log``: WRITE/MERGE/UPDATE/DELETE/OPTIMIZE..., with
    metrics. Time travel reads any of these versions."""
    fqn = _require(fqn)
    return {"table": fqn, "history": delta_io.history(fqn)}


@router.get("/{fqn}/describe-detail", summary="DESCRIBE DETAIL (version, num files, size)")
def describe_detail(fqn: str):
    fqn = _require(fqn)
    return delta_io.describe_detail(fqn)


@router.post("/{fqn}/optimize", summary="OPTIMIZE -- compact small files into fewer large ones")
def optimize(fqn: str):
    fqn = _require(fqn)
    metrics = delta_io.optimize_compact(fqn)
    return {
        "status": "optimized",
        "note": "Bin-packing compaction reduces the small-file problem and speeds scans.",
        "metrics": metrics,
    }


@router.post("/{fqn}/zorder", summary="OPTIMIZE ... ZORDER BY (cols) -- multi-dim clustering")
def zorder(fqn: str, body: ZOrderRequest):
    fqn = _require(fqn)
    metrics = delta_io.optimize_zorder(fqn, body.columns)
    return {
        "status": "z-ordered",
        "columns": body.columns,
        "note": "Z-ordering co-locates related values for better data skipping. "
        "(Databricks' newer 'liquid clustering' supersedes Z-ORDER.)",
        "metrics": metrics,
    }


@router.post("/{fqn}/vacuum", summary="VACUUM -- remove unreferenced files (dry-run by default)")
def vacuum(fqn: str, retention_hours: int = 168, dry_run: bool = True):
    fqn = _require(fqn)
    result = delta_io.vacuum(fqn, retention_hours=retention_hours, dry_run=dry_run)
    result["note"] = (
        "VACUUM deletes data files no longer referenced by the log and older than the "
        "retention window. Dry-run lists candidates without deleting (preserves time travel)."
    )
    return result


@router.delete("/{fqn}", summary="DROP TABLE")
def drop(fqn: str):
    fqn = _require(fqn)
    import shutil

    shutil.rmtree(delta_path(fqn), ignore_errors=True)
    get_db()[Collections.TABLES].delete_one({"_id": fqn})
    return {"status": "dropped", "table": fqn}


# --------------------------------------------------------------------------- #
def _require(fqn: str) -> str:
    fqn = normalize_fqn(fqn)
    if not delta_io.table_exists(fqn):
        raise HTTPException(404, f"Delta table '{fqn}' does not exist.")
    return fqn


def _existing_schema(fqn: str) -> pa.Schema:
    # delta-rs returns an arro3 Schema; pa.schema() adapts it to a pyarrow one.
    return pa.schema(delta_io.open_table(fqn).schema().to_arrow())
