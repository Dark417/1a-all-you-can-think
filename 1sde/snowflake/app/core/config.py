"""Central configuration.

Everything is environment-driven with local-friendly defaults so the project
runs out of the box. See ``.env.example`` for the full list.
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
        self.mongo_uri: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        self.mongo_db: str = os.getenv("MONGO_DB", "snowflake_demo")
        self.use_mongomock: bool = os.getenv("USE_MONGOMOCK", "").lower() in {"1", "true", "yes"}

        self.duckdb_path: str = os.getenv("DUCKDB_PATH", "./data/warehouse.duckdb")
        self.stage_dir: Path = Path(os.getenv("STAGE_DIR", "./stages")).resolve()

        self.api_host: str = os.getenv("API_HOST", "0.0.0.0")
        self.api_port: int = int(os.getenv("API_PORT", "8000"))

        # Make sure local storage directories exist.
        self.stage_dir.mkdir(parents=True, exist_ok=True)
        if self.duckdb_path != ":memory:":
            Path(self.duckdb_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
