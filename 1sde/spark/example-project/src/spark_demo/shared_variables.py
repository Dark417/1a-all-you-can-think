"""Shared variables: broadcast variables and accumulators.

Normally each task gets its own copy of any variable it closes over. The two
shared-variable types let you share state efficiently:

  - Broadcast variable: a read-only value cached once per executor (not per
    task), e.g. a lookup table shipped to every node.
  - Accumulator: a write-only counter that workers add to and the driver reads,
    used for metrics/debugging (e.g. counting bad records).
"""
from __future__ import annotations

from pyspark.sql import SparkSession


def broadcast_lookup(spark: SparkSession, codes: list[str]) -> list[str]:
    """Use a broadcast dict to map region codes to names across the cluster."""
    sc = spark.sparkContext
    lookup = sc.broadcast({"US": "United States", "GB": "Britain", "FR": "France"})

    rdd = sc.parallelize(codes)
    resolved = rdd.map(lambda c: lookup.value.get(c, "UNKNOWN"))
    return resolved.collect()


def count_with_accumulator(spark: SparkSession, numbers: list[int]) -> dict[str, int]:
    """Count how many numbers are negative using an accumulator side-channel."""
    sc = spark.sparkContext
    negatives = sc.accumulator(0)

    def inspect(x):
        if x < 0:
            negatives.add(1)
        return x

    rdd = sc.parallelize(numbers)
    # An action is required to actually run the tasks that touch the accumulator.
    processed = rdd.map(inspect).count()
    return {"processed": processed, "negatives": negatives.value}
