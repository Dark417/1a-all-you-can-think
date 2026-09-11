"""Helpers to map Snowflake's three-level namespace (DATABASE.SCHEMA.TABLE)
onto DuckDB, which only has two levels (schema.table).

We encode the database+schema into a single physical DuckDB schema named
``DATABASE$SCHEMA`` so all three Snowflake levels survive.
"""
from __future__ import annotations

from fastapi import HTTPException


def parse_fqn(fqn: str) -> tuple[str, str, str]:
    """Split ``DB.SCHEMA.TABLE`` (SCHEMA optional -> PUBLIC)."""
    parts = fqn.replace('"', "").split(".")
    if len(parts) == 3:
        db, schema, table = parts
    elif len(parts) == 2:
        db, table = parts
        schema = "PUBLIC"
    else:
        raise HTTPException(400, f"Expected DB.SCHEMA.TABLE, got '{fqn}'")
    return db.upper(), schema.upper(), table.upper()


def phys_schema(database: str, schema: str) -> str:
    return f"{database}${schema}"


def phys_table(fqn: str) -> str:
    """Quoted physical DuckDB identifier for a Snowflake FQN."""
    db, schema, table = parse_fqn(fqn)
    return f'"{phys_schema(db, schema)}"."{table}"'


def normalize_fqn(fqn: str) -> str:
    db, schema, table = parse_fqn(fqn)
    return f"{db}.{schema}.{table}"
