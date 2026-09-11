"""User-Defined Functions: plain Python UDFs and vectorized pandas UDFs.

Rule of thumb: always prefer built-in `pyspark.sql.functions` (they run in the
JVM and are Catalyst-optimizable). When you must write custom logic, a **pandas
UDF** is far faster than a row-at-a-time Python UDF because it uses Arrow to ship
batches of columns to Python and back, avoiding per-row serialization.
"""
from __future__ import annotations

import pandas as pd
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.functions import pandas_udf, udf
from pyspark.sql.types import DoubleType, IntegerType, StringType


# --- 1. Plain Python UDF (row-at-a-time; slowest, but simplest) --------------
@udf(returnType=StringType())
def initials(name: str) -> str:
    if not name:
        return ""
    return "".join(part[0].upper() for part in name.split())


# --- 2. Scalar pandas UDF (vectorized via Arrow; operates on a pd.Series) ----
@pandas_udf(IntegerType())
def name_length(names: pd.Series) -> pd.Series:
    return names.str.len()


# --- 3. Grouped-aggregate pandas UDF (a Series -> a single scalar per group) --
@pandas_udf(DoubleType())
def geometric_mean(values: pd.Series) -> float:
    import numpy as np

    return float(np.exp(np.log(values).mean()))


def apply_scalar_udfs(df: DataFrame) -> DataFrame:
    """Apply the python UDF and the scalar pandas UDF as new columns."""
    return df.withColumn("initials", initials(F.col("name"))).withColumn(
        "name_len", name_length(F.col("name"))
    )


def apply_grouped_udf(df: DataFrame, group_col: str, value_col: str) -> DataFrame:
    """Use the grouped-aggregate pandas UDF inside groupBy().agg()."""
    return df.groupBy(group_col).agg(
        geometric_mean(F.col(value_col)).alias("geo_mean")
    )
