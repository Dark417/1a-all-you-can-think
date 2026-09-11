"""Structured Streaming.

A streaming DataFrame is an unbounded table that grows as data arrives. The same
DataFrame/SQL API used for batch applies — Spark incrementally maintains the
result. Here we use the built-in `rate` source (rows/second, no external system)
and a `memory` sink so the demo is fully self-contained and testable.

Real sources/sinks: files, Kafka, sockets; console, files, Kafka, foreachBatch.
Key concepts shown: event-time windowing, watermarks, triggers, output modes,
and checkpointing.
"""
from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F


def rate_stream(spark: SparkSession, rows_per_second: int = 10) -> DataFrame:
    """A streaming DataFrame: columns `timestamp` (event time) and `value` (long)."""
    return (
        spark.readStream.format("rate")
        .option("rowsPerSecond", rows_per_second)
        .load()
    )


def windowed_counts(stream: DataFrame) -> DataFrame:
    """Tumbling 1-second event-time windows with a watermark for late data."""
    return (
        stream.withWatermark("timestamp", "5 seconds")
        .groupBy(F.window("timestamp", "1 second"))
        .agg(F.count("*").alias("n"), F.sum("value").alias("sum"))
    )


def run_for(
    spark: SparkSession,
    checkpoint_dir: str,
    rows_per_second: int = 50,
    seconds: int = 3,
) -> list[dict]:
    """Run the windowed aggregation against an in-memory sink and return rows.

    Uses output mode `complete` (the full result table each trigger) so the
    memory table reflects all windows. Checkpointing gives exactly-once recovery.
    """
    stream = rate_stream(spark, rows_per_second)
    result = windowed_counts(stream)

    query = (
        result.writeStream.format("memory")
        .queryName("win_counts")
        .outputMode("complete")
        .option("checkpointLocation", checkpoint_dir)
        .start()
    )
    try:
        query.awaitTermination(seconds)
    finally:
        query.stop()

    return [row.asDict() for row in spark.sql("SELECT * FROM win_counts").collect()]
