"""Performance: caching, partitioning, broadcast joins, and plan inspection.

These are the levers you pull to make Spark jobs fast and stable.
"""
from __future__ import annotations

from pyspark import StorageLevel
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F


def cache_and_reuse(df: DataFrame) -> tuple[int, int]:
    """Persist a DataFrame so multiple actions don't recompute the lineage.

    Returns (count, distinct_count). Without caching, each action would re-run
    the whole upstream plan; with caching the materialized result is reused.
    """
    df.persist(StorageLevel.MEMORY_AND_DISK)
    try:
        total = df.count()  # first action materializes & caches
        distinct = df.distinct().count()  # reuses cached partitions
        return total, distinct
    finally:
        df.unpersist()


def repartition_vs_coalesce(df: DataFrame) -> dict[str, int]:
    """repartition (full shuffle, can grow/shrink) vs coalesce (no shuffle, shrink)."""
    more = df.repartition(8)
    fewer = more.coalesce(2)
    return {
        "original": df.rdd.getNumPartitions(),
        "repartitioned": more.rdd.getNumPartitions(),
        "coalesced": fewer.rdd.getNumPartitions(),
    }


def broadcast_join(large: DataFrame, small: DataFrame, on: str) -> DataFrame:
    """Force a broadcast (map-side) join: ship `small` to every executor instead
    of shuffling `large`. Ideal when one side is small enough to fit in memory.
    """
    return large.join(F.broadcast(small), on, "inner")


def explain_plan(df: DataFrame) -> str:
    """Capture the physical plan string (what you'd see from df.explain(True))."""
    return df._jdf.queryExecution().toString()


def has_broadcast_in_plan(df: DataFrame) -> bool:
    """Inspect the physical plan to confirm a broadcast strategy was chosen."""
    plan = df._jdf.queryExecution().executedPlan().toString()
    return "BroadcastHashJoin" in plan or "Broadcast" in plan
