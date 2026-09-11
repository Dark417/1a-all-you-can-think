"""Raw SQL passthrough -- run any DuckDB/Snowflake-style SQL on a warehouse and
get back columns, rows, timing, credits and cache status."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core.engine import get_engine
from ..models import SqlRequest

router = APIRouter(prefix="/sql", tags=["4. SQL execution"])


@router.post("", summary="Execute SQL on a warehouse")
def run_sql(body: SqlRequest):
    try:
        return get_engine().run(
            body.sql, warehouse=body.warehouse, role=body.role, use_cache=body.use_cache
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
