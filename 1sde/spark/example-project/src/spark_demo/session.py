"""SparkSession construction and configuration.

The SparkSession is the single entry point to all Spark functionality (it wraps
the older SparkContext, SQLContext, and HiveContext). For local development we
run on `local[*]`, which uses every CPU core as an in-process worker thread.
"""
from __future__ import annotations

import os
import sys

from pyspark.sql import SparkSession

# Apache Arrow (used by pandas UDFs / toPandas) needs deep reflective access to
# java.nio on Java 17+/21. Without these flags you hit
# "sun.misc.Unsafe or java.nio.DirectByteBuffer.<init> not available".
# In `local` mode the driver JVM is launched by PySpark itself, so these must be
# supplied at JVM-launch time via PYSPARK_SUBMIT_ARGS (spark.driver.extraJavaOptions
# is too late — the JVM is already running by the time the SparkSession reads it).
_ADD_OPENS = (
    "-Dio.netty.tryReflectionSetAccessible=true "
    "--add-opens=java.base/java.nio=ALL-UNNAMED "
    "--add-opens=java.base/java.lang=ALL-UNNAMED "
    "--add-opens=java.base/sun.nio.ch=ALL-UNNAMED "
    "--add-opens=java.base/java.util=ALL-UNNAMED"
)


def _ensure_runtime_env() -> None:
    """Configure JVM flags and the Python interpreter before the JVM starts."""
    existing = os.environ.get("PYSPARK_SUBMIT_ARGS", "")
    if "--add-opens" not in existing:
        # PYSPARK_SUBMIT_ARGS is shlex-parsed and must end with `pyspark-shell`.
        os.environ["PYSPARK_SUBMIT_ARGS"] = (
            f'--driver-java-options "{_ADD_OPENS}" pyspark-shell'
        )
    # Make the driver and the Python workers use the *same* interpreter (this
    # venv), so packages like pyarrow/pandas are available on both sides.
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)


def build_spark(app_name: str = "spark-demo", master: str = "local[*]") -> SparkSession:
    """Create (or reuse) a configured SparkSession.

    The configs below are the ones you most commonly tune:
      - shuffle.partitions: default 200 is wasteful for small/local data.
      - adaptive (AQE): re-optimizes the plan at runtime (skew, partition coalesce).
      - arrow: vectorizes Python <-> JVM transfer for pandas UDFs / toPandas().
    """
    _ensure_runtime_env()
    spark = (
        SparkSession.builder.appName(app_name)
        .master(master)
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.sql.execution.arrow.pyspark.enabled", "true")
        .config("spark.ui.showConsoleProgress", "false")
        .config("spark.executor.extraJavaOptions", _ADD_OPENS)
        .getOrCreate()
    )
    # Quieten the very chatty default logging for demo output.
    spark.sparkContext.setLogLevel("WARN")
    return spark
