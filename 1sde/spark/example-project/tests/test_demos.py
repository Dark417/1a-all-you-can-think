"""Tests covering every demo module, asserting on real Spark output.

The `spark` fixture (session-scoped, local[2]) comes from conftest.py.
"""
import tempfile

from spark_demo import (
    dataframe_basics,
    io_formats,
    ml_pipeline,
    optimization,
    rdd_basics,
    schemas,
    shared_variables,
    spark_sql,
    transformations,
    udfs,
    window_functions,
)


# --- RDD ---------------------------------------------------------------------
def test_word_count(spark):
    counts = rdd_basics.word_count(spark, ["hello world", "hello spark world"])
    assert counts["hello"] == 2
    assert counts["world"] == 2
    assert counts["spark"] == 1


def test_numeric_aggregations(spark):
    stats = rdd_basics.numeric_aggregations(spark, list(range(1, 11)))
    assert stats["sum"] == 55
    assert stats["min"] == 1 and stats["max"] == 10
    assert stats["mean"] == 5.5


def test_partition_inspection(spark):
    parts = rdd_basics.partition_inspection(spark, list(range(8)), n=4)
    assert len(parts) == 4
    assert sorted(x for v in parts.values() for x in v) == list(range(8))


# --- Schemas -----------------------------------------------------------------
def test_nested_schema(spark):
    df = schemas.build_nested_df(spark)
    assert "address" in df.columns and "tags" in df.columns
    row = df.where(df.id == 1).collect()[0]
    assert row["address"]["zip"] == "10001"
    assert row["tags"] == ["vip", "newsletter"]


# --- DataFrame basics --------------------------------------------------------
def test_select_and_filter(spark):
    people = dataframe_basics.sample_people(spark)
    out = dataframe_basics.select_and_filter(people)
    ages = [r["age"] for r in out.collect()]
    assert all(a >= 35 for a in ages)
    assert ages == sorted(ages, reverse=True)  # ordered desc


def test_distinct_cities(spark):
    people = dataframe_basics.sample_people(spark)
    assert dataframe_basics.distinct_cities(people) == ["LA", "NYC", "SF"]


# --- Transformations ---------------------------------------------------------
def test_aggregate_by_city(spark):
    people = dataframe_basics.sample_people(spark)
    agg = {r["city"]: r["n"] for r in transformations.aggregate_by_city(people).collect()}
    assert agg == {"LA": 2, "NYC": 2, "SF": 2}


def test_all_join_types(spark):
    people = dataframe_basics.sample_people(spark)
    orders = transformations.orders_df(spark)
    counts = transformations.all_join_types(people, orders)
    assert counts["inner"] == 2       # Alice, Bob
    assert counts["left"] == 6        # all people
    assert counts["right"] == 3       # all orders (incl. Zoe)
    assert counts["left_semi"] == 2   # people who ordered
    assert counts["left_anti"] == 4   # people who didn't


def test_set_operations(spark):
    ops = transformations.set_operations(spark)
    assert ops["union"] == [1, 2, 3, 4]
    assert ops["intersect"] == [2, 3]
    assert ops["except"] == [1]


# --- Window functions --------------------------------------------------------
def test_running_total(spark):
    sales = window_functions.sales_df(spark)
    rows = {(r["city"], r["month"]): r["running_total"]
            for r in window_functions.running_and_moving(sales).collect()}
    assert rows[("NYC", "2024-01")] == 100
    assert rows[("NYC", "2024-02")] == 250
    assert rows[("NYC", "2024-03")] == 370


def test_top_n_per_group(spark):
    sales = window_functions.sales_df(spark)
    top = window_functions.top_n_per_group(sales, n=1).collect()
    best = {r["city"]: r["revenue"] for r in top}
    assert best == {"NYC": 150, "SF": 220}


# --- Spark SQL ---------------------------------------------------------------
def test_run_sql_query(spark):
    people = dataframe_basics.sample_people(spark)
    rows = spark_sql.run_sql_query(spark, people).collect()
    cities = {r["city"] for r in rows}
    assert cities <= {"NYC", "SF", "LA"}
    assert all(r["avg_age"] is not None for r in rows)


def test_inspect_catalog(spark):
    people = dataframe_basics.sample_people(spark)
    info = spark_sql.inspect_catalog(spark, people)
    assert "people" in info["tables"]
    assert set(info["columns"]) == {"name", "age", "city"}
    assert info["has_upper_fn"] is True


# --- UDFs --------------------------------------------------------------------
def test_scalar_udfs(spark):
    people = dataframe_basics.sample_people(spark)
    out = {r["name"]: (r["initials"], r["name_len"])
           for r in udfs.apply_scalar_udfs(people).collect()}
    assert out["Alice"] == ("A", 5)
    assert out["Bob"] == ("B", 3)


def test_grouped_udf(spark):
    df = spark.createDataFrame(
        [("a", 1.0), ("a", 4.0), ("b", 2.0), ("b", 8.0)], ["g", "v"]
    )
    res = {r["g"]: r["geo_mean"] for r in udfs.apply_grouped_udf(df, "g", "v").collect()}
    assert abs(res["a"] - 2.0) < 1e-9   # sqrt(1*4)
    assert abs(res["b"] - 4.0) < 1e-9   # sqrt(2*8)


# --- I/O ---------------------------------------------------------------------
def test_parquet_roundtrip_partitioned(spark):
    people = dataframe_basics.sample_people(spark)
    with tempfile.TemporaryDirectory() as tmp:
        out = f"{tmp}/people"
        back = io_formats.csv_roundtrip_partitioned(spark, people, out, "city")
        assert back.count() == people.count()
        assert "city" in back.columns


def test_read_csv(spark):
    from pathlib import Path
    csv = Path(__file__).resolve().parents[1] / "data" / "people.csv"
    df = io_formats.read_csv(spark, str(csv))
    assert df.count() == 6
    assert set(df.columns) == {"name", "age", "city"}


# --- Optimization ------------------------------------------------------------
def test_cache_and_reuse(spark):
    people = dataframe_basics.sample_people(spark)
    total, distinct = optimization.cache_and_reuse(people)
    assert total == 6 and distinct == 6


def test_repartition_vs_coalesce(spark):
    people = dataframe_basics.sample_people(spark)
    parts = optimization.repartition_vs_coalesce(people)
    assert parts["repartitioned"] == 8
    assert parts["coalesced"] == 2


def test_broadcast_join(spark):
    people = dataframe_basics.sample_people(spark)
    orders = transformations.orders_df(spark)
    joined = optimization.broadcast_join(people, orders, "name")
    assert joined.count() == 2
    assert optimization.has_broadcast_in_plan(joined) is True


# --- Shared variables --------------------------------------------------------
def test_broadcast_lookup(spark):
    out = shared_variables.broadcast_lookup(spark, ["US", "FR", "XX"])
    assert out == ["United States", "France", "UNKNOWN"]


def test_accumulator(spark):
    res = shared_variables.count_with_accumulator(spark, [1, -2, 3, -4, 5])
    assert res["processed"] == 5
    assert res["negatives"] == 2


# --- MLlib -------------------------------------------------------------------
def test_ml_pipeline(spark):
    df = ml_pipeline.labeled_people(spark)
    metrics = ml_pipeline.train_and_evaluate(df)
    assert metrics["n_train"] > 0 and metrics["n_test"] > 0
    # Model should produce predictions with the expected schema.
    preds = metrics["model"].transform(df)
    assert "prediction" in preds.columns and "probability" in preds.columns
