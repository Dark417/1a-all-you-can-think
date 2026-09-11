"""MongoDB-backed metadata catalog == the **Unity Catalog metastore**.

Databricks splits the platform into a **control plane** and a **data plane**:

  * The *data plane* (your cloud account) holds the actual data: Delta tables on
    object storage, read/written by compute clusters.
  * The *control plane* (managed by Databricks) holds all the metadata -- the
    Unity Catalog metastore (catalogs, schemas, tables, columns, grants,
    lineage), cluster definitions, job specs, query history, the MLflow
    registry, and so on.

We emulate that separation here: **delta-rs** owns the *data* (real Delta tables
on the local filesystem) and **DuckDB** is the SQL/query compute, while
**MongoDB** owns the *metadata* -- catalogs, schemas, table registrations,
grants, lineage edges, cluster state, DBU usage, jobs, query history, etc.

If a real MongoDB is not reachable we transparently fall back to an in-memory
``mongomock`` so the demo never requires any infrastructure -- exactly the
fallback used by the sibling Snowflake project.
"""
from __future__ import annotations

import logging
from functools import lru_cache

from .config import get_settings

log = logging.getLogger("databricks_demo.catalog")


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
    # Unity Catalog metastore objects (3-level namespace catalog.schema.table)
    CATALOGS = "catalogs"
    SCHEMAS = "schemas"
    TABLES = "tables"  # both Delta tables and view registrations
    GRANTS = "grants"  # privilege grants to principals
    LINEAGE = "lineage"  # table -> table edges (Unity Catalog data lineage)

    # Compute
    CLUSTERS = "clusters"  # all-purpose / job clusters, DBU metering

    # Databricks SQL
    QUERY_HISTORY = "query_history"
    RESULT_CACHE = "result_cache"

    # Ingestion / pipelines
    AUTOLOADER = "autoloader"  # Auto Loader streams + processed-file offsets
    DLT_PIPELINES = "dlt_pipelines"  # Delta Live Tables pipeline definitions
    JOBS = "jobs"  # Workflows: multi-task jobs (DAGs)
    NOTEBOOKS = "notebooks"  # registered notebooks (cells)


def reset_catalog() -> None:
    """Drop every collection -- used by tests and the ``/admin/reset`` endpoint."""
    db = get_db()
    for name in db.list_collection_names():
        db.drop_collection(name)
