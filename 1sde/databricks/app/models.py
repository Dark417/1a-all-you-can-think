"""Pydantic request/response models.

These power the Swagger UI: every field description below shows up as inline
documentation at http://localhost:8000/docs
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ClusterSize = Literal["2X-SMALL", "X-SMALL", "SMALL", "MEDIUM", "LARGE", "X-LARGE"]


# --------------------------------------------------------------------------- #
# 1. Clusters (compute)
# --------------------------------------------------------------------------- #
class ClusterCreate(BaseModel):
    name: str = Field(..., examples=["analytics-cluster"])
    size: ClusterSize = "X-SMALL"
    cluster_type: Literal["ALL_PURPOSE", "JOB"] = Field(
        "ALL_PURPOSE", description="All-purpose (interactive) vs ephemeral job cluster."
    )
    autoscale: bool = Field(True, description="Enable autoscaling between min/max workers.")
    min_workers: int = 1
    max_workers: int = 4
    photon: bool = Field(True, description="Photon vectorized engine (always on locally via DuckDB).")


class ClusterResize(BaseModel):
    size: ClusterSize | None = None
    min_workers: int | None = None
    max_workers: int | None = None
    current_workers: int | None = Field(None, description="Manually set the active worker count.")


# --------------------------------------------------------------------------- #
# 2. Unity Catalog
# --------------------------------------------------------------------------- #
class CatalogCreate(BaseModel):
    name: str = Field(..., examples=["main"])
    comment: str | None = None


class SchemaCreate(BaseModel):
    catalog: str = Field(..., examples=["main"])
    name: str = Field(..., examples=["sales"])
    comment: str | None = None


class GrantRequest(BaseModel):
    privilege: str = Field(..., examples=["SELECT", "MODIFY", "USE_SCHEMA", "ALL_PRIVILEGES"])
    securable_type: str = Field(..., examples=["TABLE", "SCHEMA", "CATALOG"])
    securable_name: str = Field(..., examples=["main.sales.customers"])
    principal: str = Field(..., description="User or group to grant to.", examples=["data_engineers"])


class RevokeRequest(GrantRequest):
    pass


# --------------------------------------------------------------------------- #
# 3. Delta Lake
# --------------------------------------------------------------------------- #
class ColumnDef(BaseModel):
    name: str
    type: str = Field(..., examples=["INTEGER", "STRING", "DOUBLE", "TIMESTAMP", "BOOLEAN"])


class DeltaCreate(BaseModel):
    table: str = Field(..., description="catalog.schema.table", examples=["main.sales.customers"])
    columns: list[ColumnDef]
    partition_by: list[str] = Field(default_factory=list)
    cluster: str | None = Field(None, description="Cluster this DDL runs on (for DBU metering).")


class DeltaWrite(BaseModel):
    rows: list[dict[str, Any]] = Field(..., examples=[[{"id": 1, "name": "Ada"}]])
    evolve_schema: bool = Field(
        False, description="Allow new columns to be added to the table (schema evolution)."
    )


class DeltaMerge(BaseModel):
    rows: list[dict[str, Any]] = Field(..., description="Source rows to upsert.")
    key_columns: list[str] = Field(..., examples=[["id"]], description="MERGE join keys.")


class DeltaUpdate(BaseModel):
    set: dict[str, str] = Field(
        ..., description="column -> SQL expression", examples=[{"name": "'updated'"}]
    )
    predicate: str | None = Field(None, examples=["id = 1"])


class DeltaDelete(BaseModel):
    predicate: str | None = Field(None, examples=["id = 1"])


class ZOrderRequest(BaseModel):
    columns: list[str] = Field(..., examples=[["id"]])


# --------------------------------------------------------------------------- #
# 4. Databricks SQL (DBSQL)
# --------------------------------------------------------------------------- #
class SqlRequest(BaseModel):
    sql: str = Field(..., examples=["SELECT 1 AS hello"])
    cluster: str | None = Field("analytics-cluster", description="Cluster/warehouse to bill DBUs to.")
    use_cache: bool = True
    register: list[str] = Field(
        default_factory=list,
        description="Delta tables (catalog.schema.table) to expose as views before running.",
        examples=[["main.sales.customers"]],
    )


# --------------------------------------------------------------------------- #
# 5. Medallion pipeline
# --------------------------------------------------------------------------- #
class BronzeIngest(BaseModel):
    table: str = Field("main.medallion.bronze_events", description="Bronze Delta table.")
    rows: list[dict[str, Any]] = Field(..., description="Raw records to land as-is.")


class SilverBuild(BaseModel):
    source: str = "main.medallion.bronze_events"
    target: str = "main.medallion.silver_events"
    dedupe_key: str = Field("event_id", description="Column used to drop duplicates.")
    drop_nulls_in: list[str] = Field(default_factory=list, description="Required (non-null) columns.")
    cluster: str | None = None


class GoldBuild(BaseModel):
    source: str = "main.medallion.silver_events"
    target: str = "main.medallion.gold_event_counts"
    group_by: list[str] = Field(..., examples=[["event_type"]])
    cluster: str | None = None


# --------------------------------------------------------------------------- #
# 6. Auto Loader / Structured Streaming
# --------------------------------------------------------------------------- #
class AutoloaderCreate(BaseModel):
    name: str = Field(..., examples=["events_loader"])
    source_dir: str = Field(..., description="Subdir of STAGE_DIR to watch for new files.")
    format: Literal["csv", "json", "parquet"] = "json"
    target: str = Field("main.bronze.raw_events", description="Bronze Delta table to ingest into.")


class AutoloaderTrigger(BaseModel):
    trigger_once: bool = Field(True, description="Process all currently-available new files once.")
    cluster: str | None = None


# --------------------------------------------------------------------------- #
# 7. Delta Live Tables
# --------------------------------------------------------------------------- #
class DLTExpectation(BaseModel):
    name: str = Field(..., examples=["valid_amount"])
    constraint: str = Field(..., description="Boolean SQL expr rows must satisfy.", examples=["amount > 0"])
    action: Literal["WARN", "DROP", "FAIL"] = Field(
        "DROP", description="WARN=keep+report, DROP=quarantine, FAIL=abort."
    )


class DLTStep(BaseModel):
    name: str = Field(..., description="Output table name (within the pipeline target schema).")
    query: str = Field(..., description="SQL producing this table; reference upstream steps by name.")
    depends_on: list[str] = Field(default_factory=list, description="Upstream step names.")
    expectations: list[DLTExpectation] = Field(default_factory=list)


class DLTPipelineCreate(BaseModel):
    name: str = Field(..., examples=["sales_pipeline"])
    target_catalog: str = "main"
    target_schema: str = "dlt"
    steps: list[DLTStep]


class DLTRunRequest(BaseModel):
    cluster: str | None = None


# --------------------------------------------------------------------------- #
# 8. Jobs / Workflows
# --------------------------------------------------------------------------- #
class JobTask(BaseModel):
    key: str = Field(..., description="Unique task key within the job.", examples=["build_silver"])
    sql: str = Field(..., description="SQL executed when the task runs.")
    depends_on: list[str] = Field(default_factory=list, description="Task keys this task waits for.")


class JobCreate(BaseModel):
    name: str = Field(..., examples=["nightly_etl"])
    tasks: list[JobTask]
    cluster: str = "analytics-cluster"
    schedule_seconds: int | None = Field(None, description="Run every N seconds (cron analogue).")


# --------------------------------------------------------------------------- #
# 9. Notebooks
# --------------------------------------------------------------------------- #
class NotebookCell(BaseModel):
    language: Literal["sql", "python"] = "sql"
    source: str


class NotebookCreate(BaseModel):
    name: str = Field(..., examples=["explore"])
    cells: list[NotebookCell]


class NotebookRun(BaseModel):
    cluster: str | None = "analytics-cluster"


# --------------------------------------------------------------------------- #
# 10. MLflow
# --------------------------------------------------------------------------- #
class ExperimentCreate(BaseModel):
    name: str = Field(..., examples=["churn-model"])


class RunLog(BaseModel):
    experiment: str = Field(..., examples=["churn-model"])
    run_name: str = "run-1"
    params: dict[str, Any] = Field(default_factory=dict, examples=[{"alpha": 0.5}])
    metrics: dict[str, float] = Field(default_factory=dict, examples=[{"rmse": 0.12}])
    tags: dict[str, str] = Field(default_factory=dict, examples=[{"team": "ml"}])
    register_as: str | None = Field(
        None, description="If set, log a trivial pyfunc model and register it under this name."
    )


class TransitionStage(BaseModel):
    model: str = Field(..., examples=["churn-model"])
    version: int
    stage: Literal["Staging", "Production", "Archived", "None"] = "Staging"
