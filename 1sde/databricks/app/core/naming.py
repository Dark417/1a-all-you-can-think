"""Helpers for Unity Catalog's **three-level namespace**: ``catalog.schema.table``.

Unity Catalog introduced a true 3-level namespace (a big change from the older
2-level ``database.table`` Hive metastore). Every table is addressed as
``catalog.schema.table``. We keep that addressing everywhere and map each table
to a physical on-disk Delta location of the form::

    <DELTA_DIR>/<catalog>/<schema>/<table>

so the filesystem layout literally mirrors the namespace.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from .config import get_settings


def parse_fqn(fqn: str) -> tuple[str, str, str]:
    """Split ``catalog.schema.table`` (schema optional -> ``default``)."""
    parts = fqn.replace('"', "").split(".")
    if len(parts) == 3:
        cat, schema, table = parts
    elif len(parts) == 2:
        cat, table = parts
        schema = "default"
    else:
        raise HTTPException(400, f"Expected catalog.schema.table, got '{fqn}'")
    return cat.lower(), schema.lower(), table.lower()


def normalize_fqn(fqn: str) -> str:
    """Canonical lower-cased ``catalog.schema.table`` string used as the Mongo _id."""
    cat, schema, table = parse_fqn(fqn)
    return f"{cat}.{schema}.{table}"


def delta_path(fqn: str) -> str:
    """Absolute on-disk path of the Delta table for an FQN.

    The path mirrors the namespace: ``<DELTA_DIR>/catalog/schema/table``.
    """
    cat, schema, table = parse_fqn(fqn)
    return str(get_settings().delta_dir / cat / schema / table)


def ensure_parent(fqn: str) -> Path:
    """Create (and return) the parent directory for a table's Delta location."""
    p = Path(delta_path(fqn))
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
