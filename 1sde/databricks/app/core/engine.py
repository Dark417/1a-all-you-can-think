"""DuckDB-backed query engine == the **Databricks SQL warehouse / Photon**.

Databricks separates **storage** (Delta tables on object storage) from
**compute** (clusters / SQL warehouses). Many independent clusters of different
sizes read and write the *same* Delta tables; each cluster is billed in **DBUs**
(Databricks Units) per second while running, scaled by its size.

Locally:
  * **delta-rs** owns the storage layer (see ``delta_io.py``).
  * **DuckDB** is the vectorised, Photon-style query engine. It reads Delta
    tables directly via the ``delta`` extension's ``delta_scan('<path>')``.
  * Each "cluster" is a logical compute object in MongoDB whose state (size,
    RUNNING/TERMINATED, autoscaling workers, DBUs consumed) we meter. A cluster's
    size sets DuckDB's thread budget -- a concrete analogue of "more workers".
  * A query **result cache** (in MongoDB) mirrors Databricks SQL's result reuse.

Crucially, the SQL engine and the storage are decoupled: DuckDB can be
``:memory:`` and throw-away, while the Delta tables persist on disk -- exactly
Databricks' "compute is ephemeral, the Lakehouse is durable" model.
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
from .naming import delta_path, normalize_fqn

# DBUs-per-second by cluster size. Databricks bills DBUs/hour that roughly double
# each size tier; we keep the ratios and scale to per-second so demo queries show
# realistic tiny numbers.
CLUSTER_DBU_RATE = {
    "2X-SMALL": 1 / 3600,
    "X-SMALL": 2 / 3600,
    "SMALL": 4 / 3600,
    "MEDIUM": 8 / 3600,
    "LARGE": 16 / 3600,
    "X-LARGE": 32 / 3600,
}

# DuckDB threads granted per cluster size -- the analogue of "more worker nodes".
CLUSTER_THREADS = {
    "2X-SMALL": 1,
    "X-SMALL": 1,
    "SMALL": 2,
    "MEDIUM": 4,
    "LARGE": 8,
    "X-LARGE": 8,
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Engine:
    """Process-wide singleton wrapping a single DuckDB connection with the
    ``delta`` extension loaded so it can ``delta_scan`` real Delta tables."""

    _instance: "Engine | None" = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        settings = get_settings()
        self.con = duckdb.connect(settings.duckdb_path)
        self.con.execute("INSTALL json; LOAD json;")
        # The delta extension lets DuckDB read Delta tables natively. If it can't
        # be loaded (offline), we fall back to registering Arrow tables instead.
        self.delta_native = False
        try:
            self.con.execute("INSTALL delta; LOAD delta;")
            self.delta_native = True
        except Exception:  # noqa: BLE001 - degrade gracefully
            self.delta_native = False
        self._exec_lock = threading.Lock()

    @classmethod
    def instance(cls) -> "Engine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = Engine()
            return cls._instance

    # ------------------------------------------------------------------ #
    # Make a Delta table queryable from SQL as `catalog.schema.table`.
    # ------------------------------------------------------------------ #
    def register_delta(self, fqn: str) -> str:
        """Expose a Delta table to DuckDB and return the SQL identifier to use.

        Preferred path: a DuckDB VIEW over ``delta_scan('<path>')`` (zero-copy,
        reads the live table). Fallback: read the table into Arrow and register
        it. Either way the caller queries a stable view name.
        """
        fqn = normalize_fqn(fqn)
        view = _view_name(fqn)
        path = delta_path(fqn)
        with self._exec_lock:
            if self.delta_native:
                self.con.execute(
                    f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM delta_scan('{path}')"
                )
            else:  # pragma: no cover - only hit when the extension is unavailable
                from deltalake import DeltaTable

                arrow = DeltaTable(path).to_pyarrow_table()
                self.con.register(f"_arrow_{view}", arrow)
                self.con.execute(f"CREATE OR REPLACE VIEW {view} AS SELECT * FROM _arrow_{view}")
        return view

    # ------------------------------------------------------------------ #
    # Cluster-aware query execution with DBU metering + result cache.
    # ------------------------------------------------------------------ #
    def run(
        self,
        sql: str,
        cluster: str | None = None,
        use_cache: bool = True,
        params: list | None = None,
    ) -> dict[str, Any]:
        """Execute ``sql`` "on" a cluster and record it in query history.

        Returns columns, rows, timing, DBUs and cache status -- mirroring the
        Databricks SQL query history / query profile.
        """
        db = get_db()
        started = utcnow()
        cache_key = hashlib.sha256(sql.strip().lower().encode()).hexdigest()

        # 1) Result cache (Databricks SQL reuses identical-query results).
        if use_cache and _is_read_only(sql):
            cached = db[Collections.RESULT_CACHE].find_one({"_id": cache_key})
            if cached:
                self._record_history(sql, cluster, started, 0.0, True, len(cached["rows"]))
                return {
                    "columns": cached["columns"],
                    "rows": cached["rows"],
                    "row_count": len(cached["rows"]),
                    "elapsed_ms": 0,
                    "dbus_used": 0.0,
                    "from_cache": True,
                    "cluster": cluster,
                }

        # 2) Apply the cluster's thread budget, then execute.
        threads = self._apply_cluster(cluster)
        t0 = time.perf_counter()
        with self._exec_lock:
            if threads:
                self.con.execute(f"PRAGMA threads={threads}")
            cur = self.con.execute(sql, params or [])
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = [list(r) for r in cur.fetchall()] if cur.description else []
        elapsed = time.perf_counter() - t0

        # 3) Meter DBUs against the cluster and persist usage.
        dbus = self._charge_dbus(cluster, elapsed)

        # 4) Populate the result cache for read-only queries.
        rows_json = _jsonable(rows)
        if use_cache and _is_read_only(sql):
            db[Collections.RESULT_CACHE].replace_one(
                {"_id": cache_key},
                {"_id": cache_key, "columns": columns, "rows": rows_json, "cached_at": utcnow()},
                upsert=True,
            )

        self._record_history(sql, cluster, started, dbus, False, len(rows))
        return {
            "columns": columns,
            "rows": rows_json,
            "row_count": len(rows),
            "elapsed_ms": round(elapsed * 1000, 2),
            "dbus_used": round(dbus, 8),
            "from_cache": False,
            "cluster": cluster,
        }

    # ------------------------------------------------------------------ #
    def _apply_cluster(self, cluster: str | None) -> int | None:
        if not cluster:
            return None
        db = get_db()
        c = db[Collections.CLUSTERS].find_one({"_id": cluster})
        if not c:
            raise ValueError(f"Cluster '{cluster}' does not exist. Create it first.")
        if c.get("state") == "TERMINATED":
            # Auto-start, like a Databricks cluster restarting when a query arrives.
            db[Collections.CLUSTERS].update_one(
                {"_id": cluster},
                {"$set": {"state": "RUNNING", "started_at": utcnow()}},
            )
        return CLUSTER_THREADS.get(c.get("size", "X-SMALL"), 1)

    def _charge_dbus(self, cluster: str | None, elapsed_s: float) -> float:
        if not cluster:
            return 0.0
        db = get_db()
        c = db[Collections.CLUSTERS].find_one({"_id": cluster})
        rate = CLUSTER_DBU_RATE.get(c.get("size", "X-SMALL"), CLUSTER_DBU_RATE["X-SMALL"])
        # Autoscaling: bigger clusters scale DBU/s by current worker count.
        workers = max(1, int(c.get("current_workers", c.get("min_workers", 1))))
        dbus = rate * elapsed_s * workers
        db[Collections.CLUSTERS].update_one(
            {"_id": cluster},
            {"$inc": {"dbus_used": dbus, "query_count": 1}},
        )
        return dbus

    def _record_history(self, sql, cluster, started, dbus, cached, rows):
        get_db()[Collections.QUERY_HISTORY].insert_one(
            {
                "sql": sql,
                "cluster": cluster,
                "started_at": started,
                "ended_at": utcnow(),
                "dbus_used": round(dbus, 8),
                "from_cache": cached,
                "rows_produced": rows,
            }
        )


def _view_name(fqn: str) -> str:
    """A safe DuckDB view identifier for an FQN (dots -> double underscores)."""
    return '"' + fqn.replace(".", "__") + '"'


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
