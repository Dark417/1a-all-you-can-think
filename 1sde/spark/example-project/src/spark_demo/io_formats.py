"""Reading and writing data: CSV, JSON, and Parquet, plus partitioned output.

Spark's DataSource API gives a uniform `read`/`write` surface across formats.
Parquet is the default for analytics: columnar, compressed, with predicate &
projection pushdown. CSV/JSON are convenient but row-oriented and untyped.
"""
from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession


def read_csv(spark: SparkSession, path: str, schema=None) -> DataFrame:
    """Read CSV with header. Provide a schema to skip the inference scan."""
    reader = spark.read.option("header", True)
    if schema is not None:
        return reader.schema(schema).csv(path)
    return reader.option("inferSchema", True).csv(path)


def write_parquet(df: DataFrame, path: str, partition_by: list[str] | None = None) -> None:
    """Write Parquet, optionally Hive-partitioned by the given columns."""
    writer = df.write.mode("overwrite").format("parquet")
    if partition_by:
        writer = writer.partitionBy(*partition_by)
    writer.save(path)


def read_parquet(spark: SparkSession, path: str) -> DataFrame:
    return spark.read.parquet(path)


def round_trip_json(df: DataFrame, spark: SparkSession, path: str) -> DataFrame:
    """Write then re-read JSON to demonstrate a lossless round trip."""
    df.write.mode("overwrite").json(path)
    return spark.read.json(path)


def csv_roundtrip_partitioned(
    spark: SparkSession, df: DataFrame, out_dir: str, partition_col: str
) -> DataFrame:
    """Write partitioned Parquet, then read it back (partition column preserved)."""
    write_parquet(df, out_dir, partition_by=[partition_col])
    return read_parquet(spark, out_dir)
