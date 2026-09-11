"""Delta Lake helpers -- the **Lakehouse storage layer**, powered by delta-rs.

This is the centerpiece of the demo. Unlike the Snowflake project (which used a
DuckDB file as opaque storage), here we write **genuine Delta tables** to disk
via ``deltalake`` (delta-rs, a pure-Rust implementation -- no Spark, no JVM).

A Delta table on disk is just:

  * a ``_delta_log/`` directory of ordered JSON commits (the *transaction log*),
  * plus immutable **Parquet** data files.

Because delta-rs writes the exact same open format Databricks uses, everything
here is *real*: ACID commits, MERGE upserts, UPDATE/DELETE, time travel
(``load_as_version``), schema evolution (``schema_mode="merge"``), OPTIMIZE
(file compaction), Z-ORDER, and VACUUM all genuinely work and produce a table
you could copy to S3 and open from a Databricks cluster unchanged.

All functions here are thin, well-typed wrappers so the routers stay readable.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pyarrow as pa
from deltalake import DeltaTable, write_deltalake

from .naming import delta_path, ensure_parent, normalize_fqn


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Construction helpers
# --------------------------------------------------------------------------- #
def rows_to_arrow(rows: list[dict[str, Any]], schema: pa.Schema | None = None) -> pa.Table:
    """Turn a list of row dicts into an Arrow table (the unit delta-rs writes)."""
    if schema is not None:
        # Project every row onto the declared schema so missing keys become null
        # and column order is stable.
        cols = {f.name: [r.get(f.name) for r in rows] for f in schema}
        return pa.table(cols, schema=schema)
    if not rows:
        return pa.table({})
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    return pa.table({k: [r.get(k) for r in rows] for k in keys})


def table_exists(fqn: str) -> bool:
    return DeltaTable.is_deltatable(delta_path(fqn))


def open_table(fqn: str, version: int | None = None) -> DeltaTable:
    """Open the Delta table, optionally pinned to a historical ``version``."""
    dt = DeltaTable(delta_path(fqn))
    if version is not None:
        dt.load_as_version(version)
    return dt


# --------------------------------------------------------------------------- #
# Writes
# --------------------------------------------------------------------------- #
def create_or_overwrite(fqn: str, data: pa.Table, partition_by: list[str] | None = None) -> None:
    """Create a brand-new Delta table (or fully overwrite an existing one)."""
    ensure_parent(fqn)
    write_deltalake(
        delta_path(fqn),
        data,
        mode="overwrite",
        name=normalize_fqn(fqn),
        partition_by=partition_by,
    )


def append(fqn: str, data: pa.Table, evolve_schema: bool = False) -> None:
    """Append rows. With ``evolve_schema`` new columns are merged into the
    table schema on write -- Delta's **schema evolution**."""
    ensure_parent(fqn)
    write_deltalake(
        delta_path(fqn),
        data,
        mode="append",
        schema_mode="merge" if evolve_schema else None,
    )


def merge_upsert(fqn: str, source: pa.Table, key_columns: list[str]) -> dict[str, Any]:
    """MERGE INTO ... the Delta upsert primitive.

    Rows matching on ``key_columns`` are updated; unmatched source rows are
    inserted. This is *the* operation that makes Delta a warehouse-grade table
    format rather than an append-only log.
    """
    dt = open_table(fqn)
    predicate = " AND ".join(f"t.{c} = s.{c}" for c in key_columns)
    result = (
        dt.merge(source, predicate=predicate, source_alias="s", target_alias="t", merge_schema=True)
        .when_matched_update_all()
        .when_not_matched_insert_all()
        .execute()
    )
    return _jsonable(result)


def update(fqn: str, set_expr: dict[str, str], predicate: str | None) -> dict[str, Any]:
    """UPDATE ... SET col = <expr> WHERE <predicate> (SQL expressions)."""
    return _jsonable(open_table(fqn).update(updates=set_expr, predicate=predicate))


def delete(fqn: str, predicate: str | None) -> dict[str, Any]:
    """DELETE FROM ... WHERE <predicate>."""
    return _jsonable(open_table(fqn).delete(predicate=predicate))


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #
def read_rows(fqn: str, version: int | None = None, limit: int | None = None) -> dict[str, Any]:
    """Read a Delta table (optionally a past version) as columns + JSON rows."""
    dt = open_table(fqn, version=version)
    tbl = dt.to_pyarrow_table()
    if limit is not None:
        tbl = tbl.slice(0, limit)
    return arrow_to_result(tbl, version=dt.version())


def count(fqn: str, version: int | None = None) -> int:
    return open_table(fqn, version=version).to_pyarrow_table().num_rows


def history(fqn: str) -> list[dict[str, Any]]:
    """The Delta transaction-log history -- every commit, newest first.

    Each entry carries the operation (WRITE/MERGE/UPDATE/DELETE/OPTIMIZE...),
    its parameters, and metrics. This is what powers time travel.
    """
    out = []
    for h in open_table(fqn).history():
        out.append(_jsonable(dict(h)))
    return out


def describe_detail(fqn: str) -> dict[str, Any]:
    """DESCRIBE DETAIL -- current version, file count, total size, schema, etc."""
    dt = open_table(fqn)
    add_actions = pa.table(dt.get_add_actions())
    num_files = add_actions.num_rows
    size_bytes = 0
    if "size_bytes" in add_actions.column_names and num_files:
        size_bytes = int(pa.compute.sum(add_actions["size_bytes"]).as_py() or 0)
    meta = dt.metadata()
    schema_fields = [{"name": f.name, "type": str(f.type)} for f in dt.schema().fields]
    return {
        "name": meta.name,
        "location": dt.table_uri,
        "format": "delta",
        "version": dt.version(),
        "num_files": num_files,
        "size_bytes": size_bytes,
        "partition_columns": list(meta.partition_columns),
        "num_columns": len(schema_fields),
        "schema": schema_fields,
        "created_time": meta.created_time,
    }


# --------------------------------------------------------------------------- #
# Maintenance: OPTIMIZE / Z-ORDER / VACUUM
# --------------------------------------------------------------------------- #
def optimize_compact(fqn: str) -> dict[str, Any]:
    """OPTIMIZE -- bin-pack many small files into fewer large ones."""
    return _jsonable(open_table(fqn).optimize.compact())


def optimize_zorder(fqn: str, columns: list[str]) -> dict[str, Any]:
    """OPTIMIZE ... ZORDER BY (cols) -- multi-dimensional clustering for
    data skipping. (Databricks' newer **liquid clustering** supersedes this.)"""
    return _jsonable(open_table(fqn).optimize.z_order(columns))


def vacuum(fqn: str, retention_hours: int, dry_run: bool = True) -> dict[str, Any]:
    """VACUUM -- list (dry run) or delete data files no longer referenced by the
    log and older than the retention window. We default to a dry run so the demo
    never destroys time-travel history."""
    dt = open_table(fqn)
    files = dt.vacuum(
        retention_hours=retention_hours,
        dry_run=dry_run,
        enforce_retention_duration=False,
    )
    return {
        "dry_run": dry_run,
        "retention_hours": retention_hours,
        "files_marked": len(files),
        "files": files[:50],
    }


# --------------------------------------------------------------------------- #
# Serialisation helpers
# --------------------------------------------------------------------------- #
def arrow_to_result(tbl: pa.Table, version: int | None = None) -> dict[str, Any]:
    cols = tbl.column_names
    pyrows = tbl.to_pylist()
    rows = [[_scalar(r.get(c)) for c in cols] for r in pyrows]
    out = {"columns": cols, "rows": rows, "row_count": len(rows)}
    if version is not None:
        out["version"] = version
    return out


def _scalar(v: Any) -> Any:
    import datetime as _dt
    import decimal

    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat()
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, bytes):
        return v.decode("utf-8", "replace")
    return v


def _jsonable(obj: Any) -> Any:
    """Recursively coerce delta-rs metric dicts to JSON-safe values."""
    import datetime as _dt

    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (_dt.datetime, _dt.date)):
        return obj.isoformat()
    if isinstance(obj, (bytes, bytearray)):
        return obj.decode("utf-8", "replace")
    return obj
