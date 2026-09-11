"""DuckDB-backed query engine = the *compute + storage* layers.

Snowflake's defining idea is the **separation of storage and compute**:

  * One shared, centralized **storage** layer holds all table data as
    immutable, columnar *micro-partitions*.
  * Many independent **virtual warehouses** (compute clusters) read from that
    same storage. They can be resized, suspended, and resumed independently and
    are billed per-second in "credits".
  * A **cloud services** layer coordinates everything (metadata, security,
    optimization, result cache).

Locally:
  * The single DuckDB database file == the shared storage layer.
  * Each "virtual warehouse" is a logical compute object whose state (size,
    running/suspended, credits consumed) lives in MongoDB. We meter wall-clock
    time against a per-size credit rate to make the billing model tangible.
  * A query result cache (also in MongoDB) mirrors Snowflake's 24h result reuse.
"""
from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime, timezone
from typing import Any

import duckdb

from .catalog import Collections, get_db
from .config import get_settings

# Credits-per-second by warehouse size. Snowflake doubles credits/hour each size
# up (XS=1, S=2, M=4 ...). We keep the ratios and scale to per-second.
WAREHOUSE_CREDIT_RATE = {
    "X-SMALL": 1 / 3600,
    "SMALL": 2 / 3600,
    "MEDIUM": 4 / 3600,
    "LARGE": 8 / 3600,
    "X-LARGE": 16 / 3600,
    "2X-LARGE": 32 / 3600,
}

# DuckDB threads we grant per warehouse size -- a concrete analogue of "more
# compute nodes per cluster".
WAREHOUSE_THREADS = {
    "X-SMALL": 1,
    "SMALL": 2,
    "MEDIUM": 4,
    "LARGE": 8,
    "X-LARGE": 8,
    "2X-LARGE": 8,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Engine:
    """Process-wide singleton wrapping a single DuckDB connection.

    DuckDB allows one writer; we serialize access with a lock, which is fine for
    a teaching demo and mirrors the fact that a warehouse processes a query at a
    time per slot.
    """

    _instance: "Engine | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        settings = get_settings()
        self.con = duckdb.connect(settings.duckdb_path)
        self.con.execute("INSTALL json; LOAD json;")
        self._exec_lock = threading.Lock()

    @classmethod
    def instance(cls) -> "Engine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = Engine()
            return cls._instance

    def reset_storage(self) -> None:
        """Drop every user-created schema/table -- the storage-layer counterpart
        to clearing the metadata catalog. Used by ``/admin/reset`` and tests."""
        with self._exec_lock:
            schemas = self.con.execute(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE catalog_name = current_database() "
                "AND schema_name NOT IN ('information_schema','pg_catalog','main')"
            ).fetchall()
            for (name,) in schemas:
                self.con.execute(f'DROP SCHEMA IF EXISTS "{name}" CASCADE')

    # ------------------------------------------------------------------
    # Warehouse-aware query execution with credit metering + result cache
    # ------------------------------------------------------------------
    def run(
        self,
        sql: str,
        warehouse: str | None = None,
        role: str = "PUBLIC",
        use_cache: bool = True,
        params: list | None = None,
    ) -> dict[str, Any]:
        """Execute ``sql`` "on" a warehouse and record it in query history.

        Returns a dict with columns, rows, timing, credits and cache status --
        mirroring the information Snowflake exposes in QUERY_HISTORY.
        """
        db = get_db()
        started = utcnow()
        cache_key = hashlib.sha256(sql.strip().lower().encode()).hexdigest()

        # 1) Result cache (Snowflake reuses results for identical queries 24h).
        if use_cache and _is_read_only(sql):
            cached = db[Collections.RESULT_CACHE].find_one({"_id": cache_key})
            if cached:
                self._record_history(sql, warehouse, role, started, 0.0, True, len(cached["rows"]))
                return {
                    "columns": cached["columns"],
                    "rows": cached["rows"],
                    "row_count": len(cached["rows"]),
                    "elapsed_ms": 0,
                    "credits_used": 0.0,
                    "from_cache": True,
                    "warehouse": warehouse,
                }

        # 2) Apply the warehouse's thread budget, then execute.
        threads = self._apply_warehouse(warehouse)
        t0 = time.perf_counter()
        with self._exec_lock:
            if threads:
                self.con.execute(f"PRAGMA threads={threads}")
            cur = self.con.execute(sql, params or [])
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = [list(r) for r in cur.fetchall()] if cur.description else []
        elapsed = time.perf_counter() - t0

        # 3) Meter credits against the warehouse and persist usage.
        credits = self._charge_credits(warehouse, elapsed)

        # 4) Populate result cache for read-only queries.
        rows_json = _jsonable(rows)
        if use_cache and _is_read_only(sql):
            db[Collections.RESULT_CACHE].replace_one(
                {"_id": cache_key},
                {"_id": cache_key, "columns": columns, "rows": rows_json, "cached_at": utcnow()},
                upsert=True,
            )

        self._record_history(sql, warehouse, role, started, credits, False, len(rows))
        return {
            "columns": columns,
            "rows": rows_json,
            "row_count": len(rows),
            "elapsed_ms": round(elapsed * 1000, 2),
            "credits_used": round(credits, 8),
            "from_cache": False,
            "warehouse": warehouse,
        }

    # ------------------------------------------------------------------
    def _apply_warehouse(self, warehouse: str | None) -> int | None:
        if not warehouse:
            return None
        db = get_db()
        wh = db[Collections.WAREHOUSES].find_one({"_id": warehouse})
        if not wh:
            raise ValueError(f"Warehouse '{warehouse}' does not exist. CREATE WAREHOUSE first.")
        if wh.get("state") == "SUSPENDED":
            # Auto-resume, just like Snowflake when a query arrives.
            db[Collections.WAREHOUSES].update_one(
                {"_id": warehouse},
                {"$set": {"state": "RUNNING", "resumed_at": utcnow()}},
            )
        return WAREHOUSE_THREADS.get(wh.get("size", "X-SMALL"), 1)

    def _charge_credits(self, warehouse: str | None, elapsed_s: float) -> float:
        if not warehouse:
            return 0.0
        db = get_db()
        wh = db[Collections.WAREHOUSES].find_one({"_id": warehouse})
        rate = WAREHOUSE_CREDIT_RATE.get(wh.get("size", "X-SMALL"), WAREHOUSE_CREDIT_RATE["X-SMALL"])
        # Snowflake bills a 60s minimum per resume; we keep it simple and bill
        # actual elapsed time so small demo queries show realistic tiny numbers.
        credits = rate * elapsed_s
        db[Collections.WAREHOUSES].update_one(
            {"_id": warehouse},
            {"$inc": {"credits_used": credits, "query_count": 1}},
        )
        return credits

    def _record_history(self, sql, warehouse, role, started, credits, cached, rows):
        get_db()[Collections.QUERY_HISTORY].insert_one(
            {
                "sql": sql,
                "warehouse": warehouse,
                "role": role,
                "started_at": started,
                "ended_at": utcnow(),
                "credits_used": round(credits, 8),
                "from_cache": cached,
                "rows_produced": rows,
            }
        )


def _is_read_only(sql: str) -> bool:
    head = sql.strip().lstrip("(").upper()
    return head.startswith(("SELECT", "WITH", "SHOW", "DESCRIBE", "DESC", "PRAGMA", "EXPLAIN"))


def _jsonable(rows: list[list]) -> list[list]:
    """Coerce DuckDB values (datetime, Decimal, bytes ...) to JSON-safe types."""
    import datetime as _dt
    import decimal

    def conv(v: Any) -> Any:
        if isinstance(v, (_dt.datetime, _dt.date)):
            return v.isoformat()
        if isinstance(v, decimal.Decimal):
            return float(v)
        if isinstance(v, bytes):
            return v.decode("utf-8", "replace")
        return v

    return [[conv(v) for v in row] for row in rows]


def get_engine() -> Engine:
    return Engine.instance()
