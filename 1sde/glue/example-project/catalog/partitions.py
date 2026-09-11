"""Glue Data Catalog *partition* operations.

Each partition is a catalog entry pointing at a sub-prefix of the table's S3
location. Query engines use these for partition pruning (only scanning prefixes
that match a WHERE clause), which cuts cost and latency on large datasets.
"""
from __future__ import annotations

from catalog.client import glue_client
from catalog.table import (
    PARQUET_INPUT_FORMAT,
    PARQUET_OUTPUT_FORMAT,
    PARQUET_SERDE,
)


def _partition_input(values: list[str], location: str, columns: list[dict]) -> dict:
    """One PartitionInput. Values must match the order of the table's PartitionKeys."""
    return {
        "Values": values,
        "StorageDescriptor": {
            "Columns": columns,
            "Location": location,
            "InputFormat": PARQUET_INPUT_FORMAT,
            "OutputFormat": PARQUET_OUTPUT_FORMAT,
            "SerdeInfo": {
                "SerializationLibrary": PARQUET_SERDE,
                "Parameters": {"serialization.format": "1"},
            },
        },
    }


def batch_add_partitions(
    database: str,
    table_name: str,
    base_location: str,
    columns: list[dict],
    partition_value_sets: list[list[str]],
    partition_key_names: list[str],
    client=None,
) -> list[dict]:
    """Add many partitions in one call (batch_create_partition handles up to 100).

    `partition_value_sets` is a list like [["2024", "01"], ["2024", "02"]] and
    `partition_key_names` is ["year", "month"]. The S3 location for each is the
    Hive-style path base_location/year=2024/month=01/.

    Returns the list of any errors reported by Glue (empty == all succeeded).
    """
    client = client or glue_client()
    base = base_location.rstrip("/")

    entries = []
    for values in partition_value_sets:
        suffix = "/".join(f"{k}={v}" for k, v in zip(partition_key_names, values))
        location = f"{base}/{suffix}/"
        entries.append(_partition_input(values, location, columns))

    errors: list[dict] = []
    # batch_create_partition accepts at most 100 entries per call.
    for i in range(0, len(entries), 100):
        chunk = entries[i : i + 100]
        resp = client.batch_create_partition(
            DatabaseName=database, TableName=table_name, PartitionInputList=chunk
        )
        errors.extend(resp.get("Errors", []))
    return errors


def list_partitions(database: str, table_name: str, client=None) -> list[list[str]]:
    """Return the value lists of all partitions, e.g. [["2024", "01"], ...]."""
    client = client or glue_client()
    result: list[list[str]] = []
    paginator = client.get_paginator("get_partitions")
    for page in paginator.paginate(DatabaseName=database, TableName=table_name):
        result.extend(p["Values"] for p in page["Partitions"])
    return result
