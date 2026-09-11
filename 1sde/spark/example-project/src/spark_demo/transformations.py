"""Aggregations, joins, and set operations.

groupBy/join are *wide* transformations: they shuffle data across the cluster
and create new stages. This module shows the full join matrix and grouped aggs.
"""
from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F


def aggregate_by_city(df: DataFrame) -> DataFrame:
    """groupBy + multiple aggregations in one pass."""
    return (
        df.groupBy("city")
        .agg(
            F.count("*").alias("n"),
            F.round(F.avg("age"), 1).alias("avg_age"),
            F.min("age").alias("min_age"),
            F.max("age").alias("max_age"),
            F.collect_list("name").alias("people"),
        )
        .orderBy("city")
    )


def pivot_example(df: DataFrame) -> DataFrame:
    """Pivot: turn distinct city values into columns of counts."""
    return df.groupBy(F.lit(1).alias("_")).pivot("city").count().drop("_")


def orders_df(spark: SparkSession) -> DataFrame:
    return spark.createDataFrame(
        [(1, "Alice", 100), (2, "Bob", 250), (3, "Zoe", 75)],
        ["order_id", "name", "amount"],
    )


def all_join_types(people: DataFrame, orders: DataFrame) -> dict[str, int]:
    """Run every join type and return row counts so behavior is observable.

    people has Alice/Bob/Carol/...; orders has Alice/Bob/Zoe. So:
      inner      -> only matching names (Alice, Bob)
      left       -> all people, orders null where unmatched
      right      -> all orders, people null where unmatched (Zoe)
      full       -> union of both sides
      left_semi  -> people rows that HAVE an order (no order columns)
      left_anti  -> people rows that have NO order
    """
    return {
        "inner": people.join(orders, "name", "inner").count(),
        "left": people.join(orders, "name", "left").count(),
        "right": people.join(orders, "name", "right").count(),
        "full": people.join(orders, "name", "full").count(),
        "left_semi": people.join(orders, "name", "left_semi").count(),
        "left_anti": people.join(orders, "name", "left_anti").count(),
    }


def set_operations(spark: SparkSession) -> dict[str, list[int]]:
    """union / intersect / except over two integer DataFrames."""
    a = spark.createDataFrame([(1,), (2,), (3,)], ["v"])
    b = spark.createDataFrame([(2,), (3,), (4,)], ["v"])

    def vals(df: DataFrame) -> list[int]:
        return sorted(r["v"] for r in df.collect())

    return {
        "union": vals(a.union(b).distinct()),
        "intersect": vals(a.intersect(b)),
        "except": vals(a.exceptAll(b)),
    }
