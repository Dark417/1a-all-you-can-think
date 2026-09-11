"""Core DataFrame relational operations.

These are the bread-and-butter transformations. All are lazy: nothing runs until
an action (count/collect/show/write) is called.
"""
from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from spark_demo.schemas import people_schema


def sample_people(spark: SparkSession) -> DataFrame:
    data = [
        ("Alice", 34, "NYC"),
        ("Bob", 45, "SF"),
        ("Carol", 29, "NYC"),
        ("Dave", 52, "LA"),
        ("Eve", 41, "SF"),
        ("Frank", 38, "LA"),
    ]
    return spark.createDataFrame(data, schema=people_schema())


def select_and_filter(df: DataFrame) -> DataFrame:
    """select / where / withColumn / orderBy — projection, predicate, derived col."""
    return (
        df.select("name", "age", "city")
        .where(F.col("age") >= 35)
        .withColumn("age_group", F.when(F.col("age") >= 45, "senior").otherwise("mid"))
        .withColumn("name_upper", F.upper(F.col("name")))
        .orderBy(F.col("age").desc())
    )


def add_derived_columns(df: DataFrame) -> DataFrame:
    """Demonstrate column expressions: arithmetic, cast, string & conditional fns."""
    return df.withColumn("decade", (F.col("age") / 10).cast("int") * 10).withColumn(
        "is_ny", F.col("city") == F.lit("NYC")
    )


def distinct_cities(df: DataFrame) -> list[str]:
    rows = df.select("city").distinct().orderBy("city").collect()
    return [r["city"] for r in rows]
