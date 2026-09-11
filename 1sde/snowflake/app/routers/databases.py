"""Databases & Schemas -- the logical containers in Snowflake's namespace
(``DATABASE.SCHEMA.OBJECT``)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core.catalog import Collections, get_db
from ..core.engine import get_engine, utcnow
from ..models import DatabaseCreate, SchemaCreate

router = APIRouter(prefix="/databases", tags=["2. Databases & Schemas"])


@router.post("", summary="CREATE DATABASE")
def create_database(body: DatabaseCreate):
    db = get_db()
    if db[Collections.DATABASES].find_one({"_id": body.name}):
        raise HTTPException(409, f"Database '{body.name}' already exists.")
    db[Collections.DATABASES].insert_one(
        {"_id": body.name, "comment": body.comment, "created_at": utcnow()}
    )
    # DuckDB schemas are flat; we namespace as DB$SCHEMA to emulate two levels.
    _create_default_public_schema(body.name)
    return {"status": "created", "database": body.name}


@router.get("", summary="SHOW DATABASES")
def list_databases():
    return [
        {"name": d["_id"], "comment": d.get("comment")}
        for d in get_db()[Collections.DATABASES].find()
    ]


@router.post("/schemas", summary="CREATE SCHEMA")
def create_schema(body: SchemaCreate):
    db = get_db()
    if not db[Collections.DATABASES].find_one({"_id": body.database}):
        raise HTTPException(404, f"Database '{body.database}' does not exist.")
    sid = f"{body.database}.{body.name}"
    if db[Collections.SCHEMAS].find_one({"_id": sid}):
        raise HTTPException(409, f"Schema '{sid}' already exists.")
    db[Collections.SCHEMAS].insert_one(
        {"_id": sid, "database": body.database, "name": body.name, "comment": body.comment}
    )
    get_engine().con.execute(f'CREATE SCHEMA IF NOT EXISTS "{_phys(body.database, body.name)}"')
    return {"status": "created", "schema": sid}


@router.get("/{database}/schemas", summary="SHOW SCHEMAS")
def list_schemas(database: str):
    return [
        {"name": s["name"], "comment": s.get("comment")}
        for s in get_db()[Collections.SCHEMAS].find({"database": database})
    ]


@router.delete("/{database}", summary="DROP DATABASE")
def drop_database(database: str):
    db = get_db()
    db[Collections.DATABASES].delete_one({"_id": database})
    db[Collections.SCHEMAS].delete_many({"database": database})
    db[Collections.TABLES].delete_many({"database": database})
    return {"status": "dropped", "database": database}


def _create_default_public_schema(database: str) -> None:
    db = get_db()
    sid = f"{database}.PUBLIC"
    if not db[Collections.SCHEMAS].find_one({"_id": sid}):
        db[Collections.SCHEMAS].insert_one(
            {"_id": sid, "database": database, "name": "PUBLIC", "comment": "default schema"}
        )
    get_engine().con.execute(f'CREATE SCHEMA IF NOT EXISTS "{_phys(database, "PUBLIC")}"')


def _phys(database: str, schema: str) -> str:
    """Physical DuckDB schema name encoding the two-level Snowflake namespace."""
    return f"{database}${schema}"
