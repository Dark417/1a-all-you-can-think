"""MongoDB-backed metadata catalog.

In real Snowflake the **Cloud Services layer** keeps all metadata (databases,
warehouses, roles, grants, query history, micro-partition statistics ...) in a
managed, transactional key-value store -- completely separate from both the
compute (virtual warehouses) and the storage layer.

We emulate that separation here: DuckDB holds the *data*, while MongoDB holds
the *metadata*. If a real MongoDB is not reachable we transparently fall back
to an in-memory ``mongomock`` so the demo never requires infrastructure.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from .config import get_settings

log = logging.getLogger("snowflake_demo.catalog")


@lru_cache(maxsize=1)
def get_db():
    """Return a MongoDB-like database handle.

    Order of preference:
      1. Real MongoDB at ``MONGO_URI`` (unless ``USE_MONGOMOCK`` is set).
      2. In-memory ``mongomock`` fallback.
    """
    settings = get_settings()

    if not settings.use_mongomock:
        try:
            from pymongo import MongoClient

            client = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=800)
            client.admin.command("ping")  # force a real connection check
            log.info("Connected to MongoDB at %s", settings.mongo_uri)
            return client[settings.mongo_db]
        except Exception as exc:  # noqa: BLE001 - any failure -> fallback
            log.warning("MongoDB unreachable (%s); using in-memory mongomock.", exc)

    import mongomock

    client = mongomock.MongoClient()
    return client[settings.mongo_db]


# Collection names used across the project. Keeping them here avoids typos.
class Collections:
    WAREHOUSES = "warehouses"
    DATABASES = "databases"
    SCHEMAS = "schemas"
    TABLES = "tables"
    STAGES = "stages"
    FILE_FORMATS = "file_formats"
    STREAMS = "streams"
    TASKS = "tasks"
    CLONES = "clones"
    TIME_TRAVEL = "time_travel"  # row-level history snapshots
    ROLES = "roles"
    GRANTS = "grants"
    USERS = "users"
    FUNCTIONS = "functions"  # UDFs + stored procedures
    SHARES = "shares"
    QUERY_HISTORY = "query_history"
    RESULT_CACHE = "result_cache"
    RESOURCE_MONITORS = "resource_monitors"
    PIPES = "pipes"  # Snowpipe


def reset_catalog() -> None:
    """Drop every collection -- used by tests and the ``/admin/reset`` endpoint."""
    db = get_db()
    for name in db.list_collection_names():
        db.drop_collection(name)
