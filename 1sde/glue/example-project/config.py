"""Central configuration for the Glue catalog example.

Values can be overridden via environment variables so the same code works in
tests (mocked), local runs, and CI.
"""
from __future__ import annotations

import os

# AWS region the Glue Data Catalog lives in (catalog is per-account, per-region).
REGION = os.environ.get("AWS_REGION", "us-east-1")

# S3 bucket that backs the table data (you must own this for real runs).
BUCKET = os.environ.get("GLUE_BUCKET", "example-data-bucket")

# Catalog object names.
DATABASE = os.environ.get("GLUE_DATABASE", "sales_db")
TABLE = os.environ.get("GLUE_TABLE", "sales")

# Root S3 prefix for the table's data.
TABLE_LOCATION = f"s3://{BUCKET}/{TABLE}/"


# Schema of the `sales` table: non-partition columns only.
# Partition columns (year, month) are declared separately as partition keys.
SALES_COLUMNS = [
    {"Name": "order_id", "Type": "string", "Comment": "Unique order identifier"},
    {"Name": "customer_id", "Type": "string", "Comment": "Customer identifier"},
    {"Name": "region", "Type": "string", "Comment": "Sales region"},
    {"Name": "amount", "Type": "double", "Comment": "Order amount in USD"},
    {"Name": "currency", "Type": "string", "Comment": "ISO currency code"},
    {"Name": "ordered_at", "Type": "timestamp", "Comment": "Order timestamp"},
]

# Partition keys live in the S3 path (Hive-style year=YYYY/month=MM/), not files.
SALES_PARTITION_KEYS = [
    {"Name": "year", "Type": "string"},
    {"Name": "month", "Type": "string"},
]
