# Exhaustive PySpark Example Project

A runnable PySpark project that demonstrates **every major Spark functionality**
described in [`../README.md`](../README.md), as small focused modules each backed
by tests.

```
example-project/
├── README.md
├── requirements.txt
├── pytest.ini
├── conftest.py                     # shared local SparkSession fixture
├── main.py                         # driver: runs all demos end to end
├── data/                           # tiny sample datasets (generated + static)
│   └── people.csv
└── src/spark_demo/
    ├── session.py                  # SparkSession builder (configs, AQE, log level)
    ├── rdd_basics.py               # RDD transformations & actions
    ├── schemas.py                  # StructType / nested schemas / inference
    ├── dataframe_basics.py         # select/filter/withColumn/orderBy
    ├── transformations.py          # groupBy/agg, joins, set ops
    ├── window_functions.py         # row_number, rank, lag/lead, running totals
    ├── spark_sql.py                # temp views, spark.sql, catalog API
    ├── udfs.py                     # python UDF + pandas UDF (Arrow)
    ├── io_formats.py               # csv/json/parquet read & write, partitioning
    ├── optimization.py             # cache, repartition/coalesce, broadcast, explain
    ├── shared_variables.py         # broadcast variables & accumulators
    ├── streaming.py                # Structured Streaming (rate source -> memory)
    └── ml_pipeline.py              # MLlib pipeline: assemble -> train -> evaluate
```

## Requirements

- **Java 17 or 21** (Spark 4.0 supports both). Check with `java -version`.
  The session builder auto-injects the `--add-opens` flags Arrow needs on
  Java 17+/21, and pins the worker interpreter, so no manual JVM setup is needed.
- Python 3.9–3.12.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run everything

```bash
python main.py
```

This builds a local SparkSession (`local[*]`) and runs each demo, printing
results. No cluster needed — `local[*]` uses all CPU cores as in-process workers.

## Run the tests

```bash
pytest -q
```

Every module has a corresponding test that asserts on real Spark output. The
SparkSession is created once per session (see `conftest.py`) for speed.

## Module guide

| Module                 | Demonstrates                                                        |
|------------------------|--------------------------------------------------------------------|
| `session.py`           | Building/configuring `SparkSession`, AQE, shuffle partitions.      |
| `rdd_basics.py`        | `map`/`flatMap`/`filter`/`reduceByKey`, actions, lineage.          |
| `schemas.py`           | Explicit `StructType`, nested structs/arrays, schema inference.    |
| `dataframe_basics.py`  | Core relational ops on DataFrames.                                 |
| `transformations.py`   | Aggregations, all join types, union/intersect/except.             |
| `window_functions.py`  | Ranking, offset (`lag`/`lead`), and running/moving aggregates.    |
| `spark_sql.py`         | Temp views, `spark.sql`, and the `spark.catalog` API.             |
| `udfs.py`              | Python UDFs and vectorized pandas UDFs.                           |
| `io_formats.py`        | Round-tripping CSV/JSON/Parquet, partitioned writes.              |
| `optimization.py`      | Caching, repartition vs coalesce, broadcast joins, `explain`.     |
| `shared_variables.py`  | Broadcast variables and accumulators.                             |
| `streaming.py`         | Structured Streaming with windows over a rate source.             |
| `ml_pipeline.py`       | A full MLlib classification pipeline with evaluation.             |
