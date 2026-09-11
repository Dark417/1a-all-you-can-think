"""Small helpers to register/auto-create Unity Catalog objects.

Shared by the ``delta``, ``medallion``, ``dlt`` and ``autoloader`` routers so
they can register the Delta tables they produce into the metastore (and
auto-create the parent catalog/schema) without duplicating code.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .catalog import Collections, get_db
from .naming import normalize_fqn, parse_fqn


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_namespace(fqn: str) -> None:
    """Auto-create the catalog and schema for ``fqn`` if they don't exist."""
    cat, schema, _ = parse_fqn(fqn)
    db = get_db()
    db[Collections.CATALOGS].update_one(
        {"_id": cat}, {"$setOnInsert": {"_id": cat, "created_at": utcnow()}}, upsert=True
    )
    sid = f"{cat}.{schema}"
    db[Collections.SCHEMAS].update_one(
        {"_id": sid},
        {"$setOnInsert": {"_id": sid, "catalog": cat, "name": schema, "created_at": utcnow()}},
        upsert=True,
    )


def register_table(fqn: str, columns: list[dict] | None = None, kind: str = "MANAGED") -> None:
    """Register (or update) a Delta table in the Unity Catalog metastore."""
    fqn = normalize_fqn(fqn)
    cat, schema, name = parse_fqn(fqn)
    ensure_namespace(fqn)
    update = {"catalog": cat, "schema": schema, "name": name, "kind": kind, "updated_at": utcnow()}
    if columns is not None:
        update["columns"] = columns
    get_db()[Collections.TABLES].update_one(
        {"_id": fqn},
        {"$set": update, "$setOnInsert": {"_id": fqn, "created_at": utcnow()}},
        upsert=True,
    )
