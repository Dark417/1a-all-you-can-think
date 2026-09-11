"""Offline tests for the catalog modules using moto to mock the Glue API.

Run with:  pytest -q
No AWS account or network access is required.
"""
from __future__ import annotations

import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

# Make the project root importable (so `import config`, `from catalog...` work).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from catalog.database import (  # noqa: E402
    create_database,
    database_exists,
    delete_database,
    list_databases,
)
from catalog.partitions import batch_add_partitions, list_partitions  # noqa: E402
from catalog.table import create_table, get_table, list_tables  # noqa: E402

REGION = "us-east-1"


@pytest.fixture
def glue():
    """A moto-mocked Glue client, injected into every catalog call."""
    with mock_aws():
        yield boto3.client("glue", region_name=REGION)


def test_database_lifecycle(glue):
    assert not database_exists("sales_db", client=glue)

    create_database("sales_db", "test", client=glue)
    assert database_exists("sales_db", client=glue)
    assert "sales_db" in list_databases(client=glue)

    # Idempotent: creating again does not raise.
    create_database("sales_db", "test", client=glue)

    delete_database("sales_db", client=glue)
    assert not database_exists("sales_db", client=glue)


def test_create_partitioned_table(glue):
    create_database(config.DATABASE, client=glue)
    create_table(
        database=config.DATABASE,
        table_name=config.TABLE,
        columns=config.SALES_COLUMNS,
        location=config.TABLE_LOCATION,
        partition_keys=config.SALES_PARTITION_KEYS,
        client=glue,
    )

    assert config.TABLE in list_tables(config.DATABASE, client=glue)

    table = get_table(config.DATABASE, config.TABLE, client=glue)
    col_names = [c["Name"] for c in table["StorageDescriptor"]["Columns"]]
    assert col_names == [c["Name"] for c in config.SALES_COLUMNS]
    assert [k["Name"] for k in table["PartitionKeys"]] == ["year", "month"]
    assert table["TableType"] == "EXTERNAL_TABLE"
    assert table["StorageDescriptor"]["Location"] == config.TABLE_LOCATION


def test_create_table_is_idempotent(glue):
    create_database(config.DATABASE, client=glue)
    for _ in range(2):
        create_table(
            database=config.DATABASE,
            table_name=config.TABLE,
            columns=config.SALES_COLUMNS,
            location=config.TABLE_LOCATION,
            partition_keys=config.SALES_PARTITION_KEYS,
            client=glue,
        )
    assert list_tables(config.DATABASE, client=glue) == [config.TABLE]


def test_batch_add_and_list_partitions(glue):
    create_database(config.DATABASE, client=glue)
    create_table(
        database=config.DATABASE,
        table_name=config.TABLE,
        columns=config.SALES_COLUMNS,
        location=config.TABLE_LOCATION,
        partition_keys=config.SALES_PARTITION_KEYS,
        client=glue,
    )

    value_sets = [["2024", "01"], ["2024", "02"], ["2024", "03"]]
    errors = batch_add_partitions(
        database=config.DATABASE,
        table_name=config.TABLE,
        base_location=config.TABLE_LOCATION,
        columns=config.SALES_COLUMNS,
        partition_value_sets=value_sets,
        partition_key_names=["year", "month"],
        client=glue,
    )
    assert errors == []

    found = list_partitions(config.DATABASE, config.TABLE, client=glue)
    assert sorted(found) == sorted(value_sets)
