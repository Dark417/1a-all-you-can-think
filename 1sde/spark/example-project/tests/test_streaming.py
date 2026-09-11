"""Structured Streaming test.

Separated from the main suite because it is timing-based (runs the stream for a
few seconds). It asserts the streaming aggregation produces window rows.
"""
import tempfile

from spark_demo import streaming


def test_windowed_stream_produces_rows(spark):
    with tempfile.TemporaryDirectory() as ckpt:
        rows = streaming.run_for(spark, ckpt, rows_per_second=100, seconds=4)

    assert len(rows) > 0
    sample = rows[0]
    assert "window" in sample and "n" in sample and "sum" in sample
    assert sample["n"] > 0
