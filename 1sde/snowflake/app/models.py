"""Pydantic request/response models.

These power the Swagger UI: every field description below shows up as inline
documentation at http://localhost:8000/docs
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

WarehouseSize = Literal[
    "X-SMALL", "SMALL", "MEDIUM", "LARGE", "X-LARGE", "2X-LARGE"
]


# --------------------------------------------------------------------------- #
# Warehouses (compute)
# --------------------------------------------------------------------------- #
class WarehouseCreate(BaseModel):
    name: str = Field(..., examples=["COMPUTE_WH"])
    size: WarehouseSize = "X-SMALL"
    auto_suspend_seconds: int = Field(60, description="Idle seconds before auto-suspend.")
    comment: str | None = None


class WarehouseResize(BaseModel):
    size: WarehouseSize


# --------------------------------------------------------------------------- #
# Databases / schemas / tables
# --------------------------------------------------------------------------- #
class DatabaseCreate(BaseModel):
    name: str = Field(..., examples=["ANALYTICS"])
    comment: str | None = None


class SchemaCreate(BaseModel):
    database: str = Field(..., examples=["ANALYTICS"])
    name: str = Field(..., examples=["PUBLIC"])
    comment: str | None = None


class ColumnDef(BaseModel):
    name: str
    type: str = Field(..., examples=["INTEGER", "VARCHAR", "VARIANT", "TIMESTAMP"])


class TableCreate(BaseModel):
    database: str = Field(..., examples=["ANALYTICS"])
    schema_name: str = Field("PUBLIC", alias="schema")
    name: str = Field(..., examples=["CUSTOMERS"])
    columns: list[ColumnDef]
    track_time_travel: bool = Field(
        True, description="Snapshot rows on every change to enable AT/BEFORE queries."
    )

    model_config = {"populate_by_name": True}


class InsertRows(BaseModel):
    rows: list[dict[str, Any]] = Field(
        ..., examples=[[{"id": 1, "name": "Ada", "profile": {"tier": "gold"}}]]
    )


# --------------------------------------------------------------------------- #
# SQL passthrough
# --------------------------------------------------------------------------- #
class SqlRequest(BaseModel):
    sql: str = Field(..., examples=["SELECT 1 AS hello"])
    warehouse: str | None = Field("COMPUTE_WH", description="Warehouse to bill the query to.")
    role: str = "ACCOUNTADMIN"
    use_cache: bool = True


# --------------------------------------------------------------------------- #
# Stages / file formats / COPY INTO / Snowpipe
# --------------------------------------------------------------------------- #
class StageCreate(BaseModel):
    name: str = Field(..., examples=["RAW_STAGE"])
    comment: str | None = None


class FileFormatCreate(BaseModel):
    name: str = Field(..., examples=["MY_CSV"])
    type: Literal["CSV", "JSON", "PARQUET"] = "CSV"
    options: dict[str, Any] = Field(
        default_factory=dict, examples=[{"header": True, "delimiter": ","}]
    )


class CopyInto(BaseModel):
    table: str = Field(..., description="Fully qualified DB.SCHEMA.TABLE")
    stage: str
    pattern: str = Field("*", description="Glob of staged files to load.")
    file_format: str
    warehouse: str = "COMPUTE_WH"


class PipeCreate(BaseModel):
    name: str
    copy_statement: CopyInto = Field(..., description="The COPY INTO run on each auto-ingest.")
    auto_ingest: bool = True


# --------------------------------------------------------------------------- #
# Streams / Tasks
# --------------------------------------------------------------------------- #
class StreamCreate(BaseModel):
    name: str = Field(..., examples=["CUSTOMERS_STREAM"])
    on_table: str = Field(..., description="Fully qualified table the stream tracks.")


class TaskCreate(BaseModel):
    name: str = Field(..., examples=["LOAD_GOLD"])
    sql: str = Field(..., description="Statement executed on each run.")
    warehouse: str = "COMPUTE_WH"
    schedule_seconds: int | None = Field(
        None, description="Run every N seconds (root task). Omit for child tasks."
    )
    after: str | None = Field(None, description="Parent task name to build a DAG.")


# --------------------------------------------------------------------------- #
# Time travel / clone
# --------------------------------------------------------------------------- #
class CloneRequest(BaseModel):
    source: str = Field(..., description="Source DB.SCHEMA.TABLE")
    target: str = Field(..., description="New DB.SCHEMA.TABLE (zero-copy).")


# --------------------------------------------------------------------------- #
# RBAC
# --------------------------------------------------------------------------- #
class RoleCreate(BaseModel):
    name: str = Field(..., examples=["DATA_ENGINEER"])


class UserCreate(BaseModel):
    name: str
    default_role: str = "PUBLIC"


class GrantRequest(BaseModel):
    privilege: str = Field(..., examples=["SELECT", "INSERT", "USAGE", "ALL"])
    on_type: str = Field(..., examples=["TABLE", "DATABASE", "WAREHOUSE", "SCHEMA"])
    on_name: str
    to_role: str


class RoleGrant(BaseModel):
    role: str = Field(..., description="Role being granted.")
    to: str = Field(..., description="Role or user that receives it.")
    to_type: Literal["ROLE", "USER"] = "ROLE"


# --------------------------------------------------------------------------- #
# UDFs / stored procedures
# --------------------------------------------------------------------------- #
class FunctionCreate(BaseModel):
    name: str = Field(..., examples=["TO_CELSIUS"])
    kind: Literal["UDF_SQL", "UDF_PYTHON", "PROCEDURE_SQL"] = "UDF_SQL"
    args: list[ColumnDef] = Field(default_factory=list)
    returns: str = "DOUBLE"
    body: str = Field(..., description="SQL expression, or Python source for python UDFs.")


# --------------------------------------------------------------------------- #
# Secure data sharing
# --------------------------------------------------------------------------- #
class ShareCreate(BaseModel):
    name: str = Field(..., examples=["SALES_SHARE"])
    objects: list[str] = Field(..., description="Fully qualified objects to expose.")
    accounts: list[str] = Field(default_factory=list, description="Consumer accounts.")


# --------------------------------------------------------------------------- #
# Resource monitors
# --------------------------------------------------------------------------- #
class ResourceMonitorCreate(BaseModel):
    name: str
    credit_quota: float = Field(..., description="Credits before the trigger fires.")
    on_breach: Literal["NOTIFY", "SUSPEND"] = "SUSPEND"
    warehouses: list[str] = Field(default_factory=list)
