"""Medallion architecture -- the flagship Databricks pipeline pattern.

Data flows through three quality tiers, each a **real Delta table**:

  * **Bronze**: raw, append-only ingestion exactly as received.
  * **Silver**: cleaned, de-duplicated, conformed (the queryable source of truth).
  * **Gold**: business-level aggregates / marts for BI and ML.

Each hop records a **Unity Catalog lineage edge** (source -> target) so the
``governance`` router can show the end-to-end graph. We use polars for the
clean/dedupe/aggregate transforms and write each layer with delta-rs.
"""
from __future__ import annotations

import polars as pl
import pyarrow as pa
from fastapi import APIRouter, HTTPException

from ..core import delta_io
from ..core.lineage import record_edge
from ..core.metastore import register_table
from ..core.naming import normalize_fqn
from ..models import BronzeIngest, GoldBuild, SilverBuild

router = APIRouter(prefix="/medallion", tags=["5. Medallion (Bronze/Silver/Gold)"])


@router.post("/bronze", summary="Bronze: append raw records as-is")
def bronze(body: BronzeIngest):
    """Land raw rows into the bronze Delta table (append-only, schema-on-write)."""
    fqn = normalize_fqn(body.table)
    if not body.rows:
        raise HTTPException(400, "No rows to ingest.")
    data = delta_io.rows_to_arrow(body.rows)
    if delta_io.table_exists(fqn):
        delta_io.append(fqn, data, evolve_schema=True)
    else:
        delta_io.create_or_overwrite(fqn, data)
    register_table(fqn, kind="MANAGED")
    dt = delta_io.open_table(fqn)
    return {
        "layer": "bronze",
        "table": fqn,
        "rows_ingested": len(body.rows),
        "version": dt.version(),
        "total_rows": dt.to_pyarrow_table().num_rows,
    }


@router.post("/silver", summary="Silver: clean + dedupe bronze into a conformed table")
def silver(body: SilverBuild):
    src = normalize_fqn(body.source)
    tgt = normalize_fqn(body.target)
    if not delta_io.table_exists(src):
        raise HTTPException(404, f"Source bronze table '{src}' does not exist.")

    df = pl.from_arrow(delta_io.open_table(src).to_pyarrow_table())
    before = df.height
    # Drop rows missing any required column, then de-duplicate on the key.
    for col in body.drop_nulls_in:
        if col in df.columns:
            df = df.filter(pl.col(col).is_not_null())
    if body.dedupe_key in df.columns:
        df = df.unique(subset=[body.dedupe_key], keep="first")
    after = df.height

    delta_io.create_or_overwrite(tgt, df.to_arrow())
    register_table(tgt, kind="MANAGED")
    record_edge(src, tgt, "silver_clean_dedupe")
    return {
        "layer": "silver",
        "source": src,
        "target": tgt,
        "rows_in": before,
        "rows_out": after,
        "rows_dropped": before - after,
        "version": delta_io.open_table(tgt).version(),
    }


@router.post("/gold", summary="Gold: aggregate silver into a business mart")
def gold(body: GoldBuild):
    src = normalize_fqn(body.source)
    tgt = normalize_fqn(body.target)
    if not delta_io.table_exists(src):
        raise HTTPException(404, f"Source silver table '{src}' does not exist.")

    df = pl.from_arrow(delta_io.open_table(src).to_pyarrow_table())
    missing = [c for c in body.group_by if c not in df.columns]
    if missing:
        raise HTTPException(400, f"group_by columns not in source: {missing}")
    agg = df.group_by(body.group_by).agg(pl.len().alias("count")).sort(body.group_by)

    # Ensure a stable, non-empty Arrow schema even when the source is empty.
    arrow = agg.to_arrow() if agg.height else pa.table(
        {**{c: pa.array([], pa.string()) for c in body.group_by}, "count": pa.array([], pa.int64())}
    )
    delta_io.create_or_overwrite(tgt, arrow)
    register_table(tgt, kind="MANAGED")
    record_edge(src, tgt, "gold_aggregate")
    return {
        "layer": "gold",
        "source": src,
        "target": tgt,
        "group_by": body.group_by,
        "rows_out": agg.height,
        "version": delta_io.open_table(tgt).version(),
        "preview": delta_io.read_rows(tgt, limit=20),
    }
