"""Tables -- structured + semi-structured (VARIANT) data, plus a peek at the
columnar "micro-partition" layout via Parquet row groups."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..core.catalog import Collections, get_db
from ..core.config import get_settings
from ..core.engine import get_engine, utcnow
from ..core.history import snapshot_table
from ..core.naming import normalize_fqn, parse_fqn, phys_schema, phys_table
from ..models import InsertRows, TableCreate

router = APIRouter(prefix="/tables", tags=["3. Tables & Semi-structured data"])

# Snowflake VARIANT -> DuckDB JSON.
_TYPE_MAP = {"VARIANT": "JSON", "OBJECT": "JSON", "ARRAY": "JSON", "STRING": "VARCHAR", "NUMBER": "DECIMAL(38,6)"}


@router.post("", summary="CREATE TABLE")
def create_table(body: TableCreate):
    db = get_db()
    fqn = f"{body.database}.{body.schema_name}.{body.name}".upper()
    if db[Collections.TABLES].find_one({"_id": fqn}):
        raise HTTPException(409, f"Table '{fqn}' already exists.")
    if not db[Collections.SCHEMAS].find_one({"_id": f"{body.database}.{body.schema_name}".upper()}):
        raise HTTPException(404, f"Schema '{body.database}.{body.schema_name}' does not exist.")

    eng = get_engine()
    eng.con.execute(f'CREATE SCHEMA IF NOT EXISTS "{phys_schema(body.database.upper(), body.schema_name.upper())}"')
    cols_sql = ", ".join(f'"{c.name}" {_TYPE_MAP.get(c.type.upper(), c.type)}' for c in body.columns)
    eng.con.execute(f"CREATE TABLE {phys_table(fqn)} ({cols_sql})")

    db[Collections.TABLES].insert_one(
        {
            "_id": fqn,
            "database": body.database.upper(),
            "schema": body.schema_name.upper(),
            "name": body.name.upper(),
            "columns": [c.model_dump() for c in body.columns],
            "track_time_travel": body.track_time_travel,
            "version": 0,
            "created_at": utcnow(),
        }
    )
    snapshot_table(fqn, "CREATE")
    return {"status": "created", "table": fqn}


@router.get("", summary="SHOW TABLES")
def list_tables():
    return [
        {"name": t["_id"], "columns": t["columns"], "version": t.get("version", 0)}
        for t in get_db()[Collections.TABLES].find()
    ]


@router.post("/{fqn}/insert", summary="INSERT rows (accepts nested JSON for VARIANT)")
def insert_rows(fqn: str, body: InsertRows):
    fqn = normalize_fqn(fqn)
    meta = _require_table(fqn)
    eng = get_engine()
    col_types = {c["name"]: c["type"].upper() for c in meta["columns"]}
    cols = list(col_types)

    for row in body.rows:
        placeholders = []
        values = []
        for c in cols:
            v = row.get(c)
            if col_types[c] in {"VARIANT", "OBJECT", "ARRAY"} and v is not None:
                placeholders.append("?::JSON")
                values.append(json.dumps(v))
            else:
                placeholders.append("?")
                values.append(v)
        eng.con.execute(
            f'INSERT INTO {phys_table(fqn)} ({", ".join(chr(34)+c+chr(34) for c in cols)}) '
            f'VALUES ({", ".join(placeholders)})',
            values,
        )
    version = snapshot_table(fqn, "INSERT")
    return {"status": "inserted", "rows": len(body.rows), "table_version": version}


@router.get("/{fqn}/data", summary="SELECT * (preview)")
def select(fqn: str, limit: int = 100, warehouse: str = "COMPUTE_WH"):
    fqn = normalize_fqn(fqn)
    _require_table(fqn)
    return get_engine().run(f"SELECT * FROM {phys_table(fqn)} LIMIT {int(limit)}", warehouse=warehouse)


@router.get(
    "/{fqn}/micro-partitions",
    summary="Inspect columnar layout (Parquet row groups ~ micro-partitions)",
)
def micro_partitions(fqn: str):
    """Snowflake stores data as immutable ~16MB columnar *micro-partitions*,
    each carrying min/max metadata used for pruning. We export the table to
    Parquet and read the row-group statistics to make this tangible."""
    fqn = normalize_fqn(fqn)
    _require_table(fqn)
    import pyarrow.parquet as pq

    settings = get_settings()
    out = Path(settings.stage_dir) / f"_mp_{fqn.replace('.', '_')}.parquet"
    get_engine().con.execute(f"COPY {phys_table(fqn)} TO '{out}' (FORMAT PARQUET, ROW_GROUP_SIZE 4)")
    pf = pq.ParquetFile(out)
    partitions = []
    for i in range(pf.metadata.num_row_groups):
        rg = pf.metadata.row_group(i)
        cols = {}
        for j in range(rg.num_columns):
            col = rg.column(j)
            stats = col.statistics
            cols[col.path_in_schema] = {
                "min": str(stats.min) if stats and stats.has_min_max else None,
                "max": str(stats.max) if stats and stats.has_min_max else None,
            }
        partitions.append({"partition": i, "rows": rg.num_rows, "column_stats": cols})
    return {
        "table": fqn,
        "explanation": "Each row group carries min/max stats Snowflake uses to PRUNE partitions.",
        "micro_partitions": partitions,
    }


@router.delete("/{fqn}", summary="DROP TABLE")
def drop_table(fqn: str):
    fqn = normalize_fqn(fqn)
    _require_table(fqn)
    get_engine().con.execute(f"DROP TABLE IF EXISTS {phys_table(fqn)}")
    get_db()[Collections.TABLES].delete_one({"_id": fqn})
    return {"status": "dropped", "table": fqn}


def _require_table(fqn: str) -> dict:
    meta = get_db()[Collections.TABLES].find_one({"_id": normalize_fqn(fqn)})
    if not meta:
        raise HTTPException(404, f"Table '{fqn}' does not exist.")
    return meta
