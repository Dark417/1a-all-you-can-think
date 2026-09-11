"""Schemas: explicit definition, nesting, and inference.

Defining schemas explicitly (instead of inferring) avoids an extra data scan,
prevents wrong type guesses, and documents intent. Spark supports rich nested
types: StructType, ArrayType, MapType.
"""
from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import (
    ArrayType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)


def people_schema() -> StructType:
    """A flat schema for the people dataset."""
    return StructType(
        [
            StructField("name", StringType(), nullable=False),
            StructField("age", IntegerType(), nullable=True),
            StructField("city", StringType(), nullable=True),
        ]
    )


def nested_schema() -> StructType:
    """A nested schema: a struct and an array-of-strings column."""
    return StructType(
        [
            StructField("id", IntegerType(), False),
            StructField(
                "address",
                StructType(
                    [
                        StructField("street", StringType(), True),
                        StructField("zip", StringType(), True),
                    ]
                ),
            ),
            StructField("tags", ArrayType(StringType()), True),
        ]
    )


def build_nested_df(spark: SparkSession) -> DataFrame:
    """Create a DataFrame with nested struct + array data."""
    rows = [
        (1, ("123 Main St", "10001"), ["vip", "newsletter"]),
        (2, ("456 Oak Ave", "94016"), ["trial"]),
    ]
    return spark.createDataFrame(rows, schema=nested_schema())


def infer_schema(spark: SparkSession) -> StructType:
    """Let Spark infer a schema from Python dicts, then return it."""
    df = spark.createDataFrame([{"x": 1, "y": "a"}, {"x": 2, "y": "b"}])
    return df.schema
