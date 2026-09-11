"""Driver that runs every demo module end to end against a local SparkSession.

    python main.py

Each section prints a small, human-readable result so you can see the feature
working. This is the "exhaustive tour" of the project.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from spark_demo import (  # noqa: E402
    dataframe_basics,
    io_formats,
    ml_pipeline,
    optimization,
    rdd_basics,
    schemas,
    shared_variables,
    spark_sql,
    streaming,
    transformations,
    udfs,
    window_functions,
)
from spark_demo.session import build_spark  # noqa: E402


def banner(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def main() -> None:
    spark = build_spark()

    banner("1. RDD basics")
    print("word_count:", rdd_basics.word_count(spark, ["hello world", "hello spark"]))
    print("aggregations:", rdd_basics.numeric_aggregations(spark, list(range(1, 11))))

    banner("2. Schemas (nested struct + array)")
    schemas.build_nested_df(spark).show(truncate=False)

    banner("3. DataFrame basics (select/filter/withColumn)")
    people = dataframe_basics.sample_people(spark)
    dataframe_basics.select_and_filter(people).show()

    banner("4. Transformations: groupBy/agg")
    transformations.aggregate_by_city(people).show(truncate=False)
    print("join row counts:", transformations.all_join_types(
        people, transformations.orders_df(spark)))
    print("set ops:", transformations.set_operations(spark))

    banner("5. Window functions")
    sales = window_functions.sales_df(spark)
    window_functions.running_and_moving(sales).show()

    banner("6. Spark SQL + catalog")
    spark_sql.run_sql_query(spark, people).show()
    print("catalog:", spark_sql.inspect_catalog(spark, people))

    banner("7. UDFs (python + pandas)")
    udfs.apply_scalar_udfs(people).show()

    banner("8. I/O formats (Parquet round trip)")
    with tempfile.TemporaryDirectory() as tmp:
        io_formats.write_parquet(people, f"{tmp}/people", partition_by=["city"])
        back = io_formats.read_parquet(spark, f"{tmp}/people")
        print("rows read back from partitioned parquet:", back.count())

    banner("9. Optimization (cache, partitions, broadcast)")
    print("cache count/distinct:", optimization.cache_and_reuse(people))
    print("partitions:", optimization.repartition_vs_coalesce(people))
    bj = optimization.broadcast_join(people, transformations.orders_df(spark), "name")
    print("broadcast in plan:", optimization.has_broadcast_in_plan(bj))

    banner("10. Shared variables (broadcast + accumulator)")
    print("broadcast lookup:", shared_variables.broadcast_lookup(spark, ["US", "FR", "XX"]))
    print("accumulator:", shared_variables.count_with_accumulator(spark, [1, -2, 3, -4, 5]))

    banner("11. Structured Streaming (rate source, windowed)")
    with tempfile.TemporaryDirectory() as ckpt:
        rows = streaming.run_for(spark, ckpt, rows_per_second=50, seconds=3)
        print(f"collected {len(rows)} window rows; sample: {rows[:2]}")

    banner("12. MLlib pipeline")
    metrics = ml_pipeline.train_and_evaluate(ml_pipeline.labeled_people(spark))
    print({k: v for k, v in metrics.items() if k != "model"})

    spark.stop()
    print("\nAll demos complete.")


if __name__ == "__main__":
    main()
