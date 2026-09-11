"""Window functions: compute over a sliding group of rows without collapsing them.

Unlike groupBy (which reduces rows), window functions keep every row and add a
value computed over a partition+ordering. Used for ranking, deduplication,
running totals, moving averages, and period-over-period deltas.
"""
from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window


def sales_df(spark: SparkSession) -> DataFrame:
    return spark.createDataFrame(
        [
            ("NYC", "2024-01", 100),
            ("NYC", "2024-02", 150),
            ("NYC", "2024-03", 120),
            ("SF", "2024-01", 200),
            ("SF", "2024-02", 180),
            ("SF", "2024-03", 220),
        ],
        ["city", "month", "revenue"],
    )


def ranking(df: DataFrame) -> DataFrame:
    """row_number / rank / dense_rank within each city by revenue desc."""
    w = Window.partitionBy("city").orderBy(F.col("revenue").desc())
    return df.select(
        "city",
        "month",
        "revenue",
        F.row_number().over(w).alias("row_number"),
        F.rank().over(w).alias("rank"),
        F.dense_rank().over(w).alias("dense_rank"),
    )


def running_and_moving(df: DataFrame) -> DataFrame:
    """Running total (unbounded) and month-over-month delta via lag."""
    ordered = Window.partitionBy("city").orderBy("month")
    running = ordered.rowsBetween(Window.unboundedPreceding, Window.currentRow)
    return df.select(
        "city",
        "month",
        "revenue",
        F.sum("revenue").over(running).alias("running_total"),
        F.lag("revenue", 1).over(ordered).alias("prev_month"),
        (F.col("revenue") - F.lag("revenue", 1).over(ordered)).alias("mom_delta"),
    )


def top_n_per_group(df: DataFrame, n: int = 1) -> DataFrame:
    """Common pattern: keep the top-N rows per partition using row_number filter."""
    w = Window.partitionBy("city").orderBy(F.col("revenue").desc())
    return (
        df.withColumn("rn", F.row_number().over(w))
        .where(F.col("rn") <= n)
        .drop("rn")
    )
