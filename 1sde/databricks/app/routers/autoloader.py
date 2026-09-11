"""Auto Loader / Structured Streaming -- incremental file ingestion.

Databricks **Auto Loader** (``cloudFiles``) incrementally and idempotently
ingests new files as they land in cloud storage, tracking which files it has
already processed in a **checkpoint** so each file is loaded exactly once. A
``trigger(once=True)`` (or ``availableNow``) micro-batch processes everything
currently available and stops -- ideal for scheduled batch-style streaming.

Here a "stream" watches a subdirectory of ``STAGE_DIR``; its checkpoint is the
set of already-processed filenames (the **offset**) stored in MongoDB. A trigger
reads only the *new* files, appends them to a bronze Delta table, and advances
the offset.
"""
from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.json as pajson
import pyarrow.parquet as papq
from fastapi import APIRouter, File, HTTPException, UploadFile

from ..core import delta_io
from ..core.catalog import Collections, get_db
from ..core.config import get_settings
from ..core.engine import utcnow
from ..core.lineage import record_edge
from ..core.metastore import register_table
from ..core.naming import normalize_fqn
from ..models import AutoloaderCreate, AutoloaderTrigger

router = APIRouter(prefix="/autoloader", tags=["6. Auto Loader / Streaming"])


def _source_path(sub: str) -> Path:
    p = Path(get_settings().stage_dir) / sub
    p.mkdir(parents=True, exist_ok=True)
    return p


@router.post("", summary="Create an Auto Loader stream watching a landing dir")
def create_stream(body: AutoloaderCreate):
    db = get_db()
    if db[Collections.AUTOLOADER].find_one({"_id": body.name}):
        raise HTTPException(409, f"Stream '{body.name}' already exists.")
    _source_path(body.source_dir)
    db[Collections.AUTOLOADER].insert_one(
        {
            "_id": body.name,
            "source_dir": body.source_dir,
            "format": body.format,
            "target": normalize_fqn(body.target),
            "processed_files": [],  # the checkpoint / offset
            "batches": 0,
            "created_at": utcnow(),
        }
    )
    return {
        "status": "created",
        "stream": body.name,
        "landing_dir": str(_source_path(body.source_dir)),
        "target": normalize_fqn(body.target),
    }


@router.put("/{name}/files", summary="Land a file into the stream's source dir")
async def land_file(name: str, file: UploadFile = File(...)):
    stream = _require(name)
    dest = _source_path(stream["source_dir"]) / file.filename
    dest.write_bytes(await file.read())
    return {"status": "landed", "file": file.filename, "size": dest.stat().st_size}


@router.post("/{name}/trigger", summary="Trigger a micro-batch (process only new files)")
def trigger(name: str, body: AutoloaderTrigger):
    """Process every file in the landing dir that is not yet in the checkpoint,
    append it to the bronze Delta table, and advance the offset. Re-running with
    no new files is a no-op (exactly-once semantics)."""
    stream = _require(name)
    src_dir = _source_path(stream["source_dir"])
    processed = set(stream.get("processed_files", []))
    all_files = sorted(p.name for p in src_dir.iterdir() if p.is_file())
    new_files = [f for f in all_files if f not in processed]

    rows_loaded = 0
    target = stream["target"]
    for fname in new_files:
        tbl = _read_file(src_dir / fname, stream["format"])
        if tbl.num_rows == 0:
            continue
        if delta_io.table_exists(target):
            delta_io.append(target, tbl, evolve_schema=True)
        else:
            delta_io.create_or_overwrite(target, tbl)
            register_table(target, kind="MANAGED")
        rows_loaded += tbl.num_rows

    get_db()[Collections.AUTOLOADER].update_one(
        {"_id": name},
        {"$set": {"processed_files": all_files}, "$inc": {"batches": 1}},
    )
    if new_files and delta_io.table_exists(target):
        record_edge(f"stage:{stream['source_dir']}", target, "auto_loader_ingest")

    return {
        "status": "triggered",
        "trigger_once": body.trigger_once,
        "new_files": new_files,
        "files_processed": len(new_files),
        "rows_loaded": rows_loaded,
        "target": target,
        "version": delta_io.open_table(target).version() if delta_io.table_exists(target) else None,
    }


@router.get("/{name}", summary="Show stream state (checkpoint / offset)")
def status(name: str):
    s = _require(name)
    return {
        "stream": name,
        "source_dir": s["source_dir"],
        "format": s["format"],
        "target": s["target"],
        "batches_run": s.get("batches", 0),
        "checkpoint_offset": {"processed_file_count": len(s.get("processed_files", []))},
        "processed_files": s.get("processed_files", []),
    }


@router.get("", summary="List Auto Loader streams")
def list_streams():
    return [
        {"name": s["_id"], "target": s["target"], "batches": s.get("batches", 0)}
        for s in get_db()[Collections.AUTOLOADER].find()
    ]


# --------------------------------------------------------------------------- #
def _read_file(path: Path, fmt: str) -> pa.Table:
    if fmt == "csv":
        return pacsv.read_csv(path)
    if fmt == "json":
        # Newline-delimited JSON, one record per line.
        return pajson.read_json(path)
    if fmt == "parquet":
        return papq.read_table(path)
    raise HTTPException(400, f"Unsupported format '{fmt}'")


def _require(name: str) -> dict:
    s = get_db()[Collections.AUTOLOADER].find_one({"_id": name})
    if not s:
        raise HTTPException(404, "Auto Loader stream not found")
    return s
