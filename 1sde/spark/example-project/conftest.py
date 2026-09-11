"""Shared pytest fixtures.

A SparkSession is expensive to start, so we create one per test session and
reuse it. `local[2]` keeps tests light while still exercising multiple partitions.
"""
import sys
from pathlib import Path

import pytest

# Ensure src/ is importable when running pytest from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from spark_demo.session import build_spark  # noqa: E402


@pytest.fixture(scope="session")
def spark():
    spark = build_spark(app_name="spark-demo-tests", master="local[2]")
    yield spark
    spark.stop()
