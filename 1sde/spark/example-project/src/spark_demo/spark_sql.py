"""Spark SQL: temp views, the spark.sql() entry point, and the Catalog API.

The DataFrame API and SQL are fully interchangeable — both compile to the same
Catalyst logical plan. Register a DataFrame as a view, then query it with SQL.
"""
from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession


def run_sql_query(spark: SparkSession, people: DataFrame) -> DataFrame:
    """Register a temp view and run an aggregating SQL query against it."""
    people.createOrReplaceTempView("people")
    return spark.sql(
        """
        SELECT city,
               COUNT(*)        AS n,
               ROUND(AVG(age), 1) AS avg_age
        FROM people
        WHERE age >= 30
        GROUP BY city
        ORDER BY avg_age DESC
        """
    )


def global_temp_view(spark: SparkSession, df: DataFrame) -> DataFrame:
    """Global temp views are visible across sessions via the global_temp database."""
    df.createOrReplaceGlobalTempView("g_people")
    return spark.sql("SELECT COUNT(*) AS total FROM global_temp.g_people")


def inspect_catalog(spark: SparkSession, people: DataFrame) -> dict:
    """Use spark.catalog to introspect databases/tables/columns/functions."""
    people.createOrReplaceTempView("people")
    return {
        "current_database": spark.catalog.currentDatabase(),
        "tables": [t.name for t in spark.catalog.listTables()],
        "columns": [c.name for c in spark.catalog.listColumns("people")],
        "has_upper_fn": any(
            f.name == "upper" for f in spark.catalog.listFunctions()
        ),
    }
