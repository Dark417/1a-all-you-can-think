"""Glue Data Catalog *table* operations.

A table is metadata describing a dataset: its schema (columns), where the data
lives (StorageDescriptor.Location), how it is serialized (SerDe / formats), and
how it is partitioned (PartitionKeys).

This module creates an EXTERNAL Parquet table — the most common shape for an S3
data lake consumed by Athena / Redshift Spectrum / Spark.
"""
from __future__ import annotations

from botocore.exceptions import ClientError

from catalog.client import glue_client

# Hadoop format + SerDe classes for Parquet. Athena/Spark read these to know how
# to deserialize the files behind the table.
PARQUET_INPUT_FORMAT = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat"
PARQUET_OUTPUT_FORMAT = "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat"
PARQUET_SERDE = "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe"


def build_parquet_table_input(
    table_name: str,
    columns: list[dict],
    location: str,
    partition_keys: list[dict] | None = None,
) -> dict:
    """Build the TableInput dict for an external, partitioned Parquet table."""
    return {
        "Name": table_name,
        "TableType": "EXTERNAL_TABLE",
        "Parameters": {
            "classification": "parquet",
            "compressionType": "snappy",
            "EXTERNAL": "TRUE",
        },
        "PartitionKeys": partition_keys or [],
        "StorageDescriptor": {
            "Columns": columns,
            "Location": location,
            "InputFormat": PARQUET_INPUT_FORMAT,
            "OutputFormat": PARQUET_OUTPUT_FORMAT,
            "SerdeInfo": {
                "SerializationLibrary": PARQUET_SERDE,
                "Parameters": {"serialization.format": "1"},
            },
            "StoredAsSubDirectories": False,
        },
    }


def create_table(
    database: str,
    table_name: str,
    columns: list[dict],
    location: str,
    partition_keys: list[dict] | None = None,
    client=None,
) -> None:
    """Create (or replace) a partitioned Parquet table in the catalog."""
    client = client or glue_client()
    table_input = build_parquet_table_input(
        table_name, columns, location, partition_keys
    )
    try:
        client.create_table(DatabaseName=database, TableInput=table_input)
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "AlreadyExistsException":
            client.update_table(DatabaseName=database, TableInput=table_input)
        else:
            raise


def get_table(database: str, table_name: str, client=None) -> dict:
    """Return the full table metadata dict."""
    client = client or glue_client()
    return client.get_table(DatabaseName=database, Name=table_name)["Table"]


def list_tables(database: str, client=None) -> list[str]:
    client = client or glue_client()
    names: list[str] = []
    paginator = client.get_paginator("get_tables")
    for page in paginator.paginate(DatabaseName=database):
        names.extend(t["Name"] for t in page["TableList"])
    return names
