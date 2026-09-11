"""Spark Core / RDD API.

RDDs are the low-level, schema-less abstraction. You reach for them for custom
partitioning, unstructured data, or fine-grained control. Most production code
should prefer DataFrames (Catalyst-optimized), but understanding RDDs explains
how Spark schedules work as narrow/wide transformations + actions.
"""
from __future__ import annotations

from pyspark.sql import SparkSession


def word_count(spark: SparkSession, lines: list[str]) -> dict[str, int]:
    """Classic word count: flatMap -> map -> reduceByKey (a wide/shuffle op)."""
    rdd = spark.sparkContext.parallelize(lines)
    counts = (
        rdd.flatMap(lambda line: line.lower().split())
        .map(lambda word: (word.strip(".,!?"), 1))
        .reduceByKey(lambda a, b: a + b)  # wide dependency -> shuffle
    )
    return dict(counts.collect())


def numeric_aggregations(spark: SparkSession, numbers: list[int]) -> dict[str, float]:
    """Demonstrate RDD actions: reduce, aggregate, stats."""
    rdd = spark.sparkContext.parallelize(numbers)
    # aggregate(zeroValue, seqOp, combOp): (sum, count) -> mean.
    total, count = rdd.aggregate(
        (0, 0),
        lambda acc, x: (acc[0] + x, acc[1] + 1),  # within partition
        lambda a, b: (a[0] + b[0], a[1] + b[1]),  # across partitions
    )
    return {
        "sum": rdd.reduce(lambda a, b: a + b),
        "min": rdd.min(),
        "max": rdd.max(),
        "mean": total / count,
        "count": count,
    }


def partition_inspection(spark: SparkSession, numbers: list[int], n: int = 4):
    """Show how data is distributed across partitions (mapPartitionsWithIndex)."""
    rdd = spark.sparkContext.parallelize(numbers, n)

    def index_partition(idx, it):
        yield (idx, list(it))

    return dict(rdd.mapPartitionsWithIndex(index_partition).collect())
