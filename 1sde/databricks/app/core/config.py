"""Central configuration.

Everything is environment-driven with local-friendly defaults so the project
runs out of the box. See ``.env.example`` for the full list.

The directory layout below mirrors how a real Databricks workspace is organised:

  * ``delta_dir``  -> the **Lakehouse storage layer**. In the cloud this is an
    S3/GCS/ADLS bucket holding Delta tables; here it is a local folder that
    delta-rs writes *genuine* Delta tables into (``_delta_log`` + Parquet).
  * ``mlruns_dir`` -> the **MLflow** tracking/registry store.
  * ``stage_dir``  -> the **Auto Loader** landing zone where raw files arrive
    before being incrementally ingested into a bronze Delta table.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# Load a .env file if python-dotenv happens to be installed; it is optional.
try:  # pragma: no cover - convenience only
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover
    pass


class Settings:
    """Resolved settings, read once at import time."""

    def __init__(self) -> None:
        # --- Metadata catalog (Unity Catalog metastore analogue) ---
        self.mongo_uri: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        self.mongo_db: str = os.getenv("MONGO_DB", "databricks_demo")
        self.use_mongomock: bool = os.getenv("USE_MONGOMOCK", "").lower() in {"1", "true", "yes"}

        # --- Databricks SQL warehouse (DuckDB) ---
        # ":memory:" keeps the SQL engine ephemeral; the *data* lives in Delta on
        # disk regardless, so durability comes from the Lakehouse, not DuckDB.
        self.duckdb_path: str = os.getenv("DUCKDB_PATH", ":memory:")

        # --- Lakehouse storage layer (delta-rs writes real Delta tables here) ---
        self.delta_dir: Path = Path(os.getenv("DELTA_DIR", "./data/delta")).resolve()

        # --- Auto Loader / Structured Streaming landing zone ---
        self.stage_dir: Path = Path(os.getenv("STAGE_DIR", "./stage")).resolve()

        # --- MLflow tracking + model registry ---
        self.mlruns_dir: Path = Path(os.getenv("MLRUNS_DIR", "./data/mlruns")).resolve()

        self.api_host: str = os.getenv("API_HOST", "0.0.0.0")
        self.api_port: int = int(os.getenv("API_PORT", "8000"))

        # Make sure local storage directories exist.
        for d in (self.delta_dir, self.stage_dir, self.mlruns_dir):
            d.mkdir(parents=True, exist_ok=True)
        if self.duckdb_path != ":memory:":
            Path(self.duckdb_path).parent.mkdir(parents=True, exist_ok=True)

    # MLflow wants a tracking URI; sqlite is the supported backend in mlflow 3.x
    # (the file store is in maintenance mode). The DB file lives under mlruns_dir
    # and the run artifacts go beside it.
    @property
    def mlflow_tracking_uri(self) -> str:
        return os.getenv("MLFLOW_TRACKING_URI", f"sqlite:///{self.mlruns_dir / 'mlflow.db'}")

    @property
    def mlflow_artifact_root(self) -> str:
        return (self.mlruns_dir / "artifacts").as_uri()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
