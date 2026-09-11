"""End-to-end bootstrap: create a database, a partitioned table, and partitions.

Run against real AWS:

    export GLUE_BUCKET=my-data-bucket
    python scripts/bootstrap_catalog.py

The script is idempotent — re-running it updates rather than fails.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running as `python scripts/bootstrap_catalog.py` from the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402
from catalog.database import create_database, list_databases  # noqa: E402
from catalog.partitions import batch_add_partitions, list_partitions  # noqa: E402
from catalog.table import create_table, get_table  # noqa: E402


def main() -> None:
    print(f"Region   : {config.REGION}")
    print(f"Database : {config.DATABASE}")
    print(f"Table    : {config.TABLE}")
    print(f"Location : {config.TABLE_LOCATION}\n")

    # 1. Database
    create_database(config.DATABASE, "Sales data lake (example)")
    print("Databases:", list_databases())

    # 2. Partitioned table
    create_table(
        database=config.DATABASE,
        table_name=config.TABLE,
        columns=config.SALES_COLUMNS,
        location=config.TABLE_LOCATION,
        partition_keys=config.SALES_PARTITION_KEYS,
    )
    table = get_table(config.DATABASE, config.TABLE)
    print(f"\nTable '{config.TABLE}' columns:")
    for col in table["StorageDescriptor"]["Columns"]:
        print(f"  - {col['Name']}: {col['Type']}")
    print("Partition keys:", [k["Name"] for k in table["PartitionKeys"]])

    # 3. Partitions for Jan-Mar 2024
    value_sets = [["2024", "01"], ["2024", "02"], ["2024", "03"]]
    errors = batch_add_partitions(
        database=config.DATABASE,
        table_name=config.TABLE,
        base_location=config.TABLE_LOCATION,
        columns=config.SALES_COLUMNS,
        partition_value_sets=value_sets,
        partition_key_names=[k["Name"] for k in config.SALES_PARTITION_KEYS],
    )
    if errors:
        print("\nPartition errors:", errors)
    print("\nPartitions now in catalog:", list_partitions(config.DATABASE, config.TABLE))
    print("\nDone. Query it in Athena with:")
    print(f"  SELECT * FROM {config.DATABASE}.{config.TABLE} WHERE year='2024' AND month='01';")


if __name__ == "__main__":
    main()
