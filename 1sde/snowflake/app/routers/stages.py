"""Stages, File Formats, COPY INTO and Snowpipe -- the bulk ingestion story.

A *stage* is a named location for data files (internal here = a local folder;
externally it would be an S3/GCS bucket). A *file format* describes how to parse
files. ``COPY INTO`` bulk-loads staged files into a table. A *pipe* (Snowpipe)
wraps a COPY statement and auto-ingests files as they land.
"""
from __future__ import annotations

import glob
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from ..core.catalog import Collections, get_db
from ..core.config import get_settings
from ..core.engine import get_engine, utcnow
from ..core.history import snapshot_table
from ..core.naming import normalize_fqn, phys_table
from ..models import CopyInto, FileFormatCreate, PipeCreate, StageCreate

router = APIRouter(prefix="/stages", tags=["5. Stages, COPY INTO & Snowpipe"])


def _stage_path(stage: str) -> Path:
    p = Path(get_settings().stage_dir) / stage
    p.mkdir(parents=True, exist_ok=True)
    return p


@router.post("", summary="CREATE STAGE")
def create_stage(body: StageCreate):
    db = get_db()
    if db[Collections.STAGES].find_one({"_id": body.name}):
        raise HTTPException(409, "Stage already exists")
    _stage_path(body.name)
    db[Collections.STAGES].insert_one({"_id": body.name, "comment": body.comment, "created_at": utcnow()})
    return {"status": "created", "stage": body.name, "location": str(_stage_path(body.name))}


@router.put("/{stage}/files", summary="PUT file @stage (upload)")
async def put_file(stage: str, file: UploadFile = File(...)):
    if not get_db()[Collections.STAGES].find_one({"_id": stage}):
        raise HTTPException(404, "Stage does not exist")
    dest = _stage_path(stage) / file.filename
    dest.write_bytes(await file.read())
    _maybe_trigger_pipes(stage)
    return {"status": "staged", "stage": stage, "file": file.filename, "size": dest.stat().st_size}


@router.get("/{stage}/files", summary="LIST @stage")
def list_files(stage: str):
    return {
        "stage": stage,
        "files": [p.name for p in _stage_path(stage).iterdir() if p.is_file()],
    }


@router.post("/file-formats", summary="CREATE FILE FORMAT")
def create_file_format(body: FileFormatCreate):
    get_db()[Collections.FILE_FORMATS].replace_one(
        {"_id": body.name},
        {"_id": body.name, "type": body.type, "options": body.options},
        upsert=True,
    )
    return {"status": "created", "file_format": body.name}


@router.post("/copy-into", summary="COPY INTO <table> FROM @stage")
def copy_into(body: CopyInto):
    return _execute_copy(body)


@router.post("/pipes", summary="CREATE PIPE (Snowpipe auto-ingest)")
def create_pipe(body: PipeCreate):
    get_db()[Collections.PIPES].replace_one(
        {"_id": body.name},
        {
            "_id": body.name,
            "auto_ingest": body.auto_ingest,
            "copy": body.copy_statement.model_dump(),
            "stage": body.copy_statement.stage,
            "files_loaded": 0,
            "created_at": utcnow(),
        },
        upsert=True,
    )
    return {"status": "created", "pipe": body.name}


@router.get("/pipes", summary="SHOW PIPES")
def list_pipes():
    return [
        {"name": p["_id"], "stage": p["stage"], "files_loaded": p.get("files_loaded", 0)}
        for p in get_db()[Collections.PIPES].find()
    ]


# --------------------------------------------------------------------------- #
def _execute_copy(body: CopyInto) -> dict:
    db = get_db()
    fmt = db[Collections.FILE_FORMATS].find_one({"_id": body.file_format})
    if not fmt:
        raise HTTPException(404, f"File format '{body.file_format}' not found")
    fqn = normalize_fqn(body.table)
    if not db[Collections.TABLES].find_one({"_id": fqn}):
        raise HTTPException(404, f"Table '{fqn}' not found")

    matches = sorted(glob.glob(str(_stage_path(body.stage) / body.pattern)))
    if not matches:
        return {"status": "nothing_to_load", "files": 0, "rows_loaded": 0}

    eng = get_engine()
    reader = _reader_sql(fmt, matches)
    before = eng.con.execute(f"SELECT COUNT(*) FROM {phys_table(fqn)}").fetchone()[0]
    eng.con.execute(f"INSERT INTO {phys_table(fqn)} BY NAME {reader}")
    after = eng.con.execute(f"SELECT COUNT(*) FROM {phys_table(fqn)}").fetchone()[0]
    snapshot_table(fqn, "LOAD")
    return {
        "status": "loaded",
        "files": len(matches),
        "rows_loaded": after - before,
        "file_names": [Path(m).name for m in matches],
    }


def _reader_sql(fmt: dict, files: list[str]) -> str:
    files_sql = "[" + ", ".join(f"'{f}'" for f in files) + "]"
    t = fmt["type"]
    opts = fmt.get("options", {})
    if t == "CSV":
        header = "true" if opts.get("header", True) else "false"
        delim = opts.get("delimiter", ",")
        return f"(SELECT * FROM read_csv({files_sql}, header={header}, delim='{delim}', auto_detect=true))"
    if t == "JSON":
        return f"(SELECT * FROM read_json_auto({files_sql}))"
    if t == "PARQUET":
        return f"(SELECT * FROM read_parquet({files_sql}))"
    raise HTTPException(400, f"Unsupported file format type {t}")


def _maybe_trigger_pipes(stage: str) -> None:
    """Snowpipe auto-ingest: when a file lands, run any pipe watching this stage."""
    db = get_db()
    for pipe in db[Collections.PIPES].find({"stage": stage, "auto_ingest": True}):
        try:
            res = _execute_copy(CopyInto(**pipe["copy"]))
            db[Collections.PIPES].update_one(
                {"_id": pipe["_id"]}, {"$inc": {"files_loaded": res.get("files", 0)}}
            )
        except HTTPException:
            pass
