# Apache Spark — Full Functionality Guide

This document explains Apache Spark end to end. The companion
[`example-project/`](./example-project) is an **exhaustive, runnable PySpark
project** that demonstrates every area described here, with tests.

---

## 1. What Spark is

Apache Spark is a distributed, in-memory data-processing engine. A single
high-level program (the *driver*) is compiled into a DAG of stages and tasks
that run in parallel across *executors* on a cluster. Spark unifies several
workloads under one engine and API:

| Library                 | Workload                                            |
|-------------------------|-----------------------------------------------------|
| **Spark Core / RDD**    | Low-level distributed collections & scheduling.     |
| **Spark SQL / DataFrame** | Structured data, SQL, the Catalyst optimizer.     |
| **Structured Streaming**| Incremental, exactly-once stream processing.        |
| **MLlib**               | Scalable machine learning (pipelines, estimators).  |
| **GraphX / GraphFrames**| Graph processing (GraphFrames is the Python path).  |

PySpark is the Python API over the JVM engine (via Py4J), plus Arrow-accelerated
pandas interop.

---

## 2. Architecture & execution model

```
            ┌─────────────┐   submits app    ┌──────────────────┐
   you ───▶ │   Driver    │ ───────────────▶ │ Cluster Manager  │
            │ SparkContext│                  │ (YARN/K8s/Stand- │
            │ SparkSession│ ◀── allocates ── │  alone/local)    │
            └─────┬───────┘                  └──────────────────┘
                  │ schedules tasks
        ┌─────────┼───────────┬───────────┐
        ▼         ▼           ▼           ▼
   ┌────────┐┌────────┐  ┌────────┐  ┌────────┐
   │Executor││Executor│  │Executor│  │Executor│   (JVM processes, N cores each)
   │ tasks  ││ tasks  │  │ tasks  │  │ tasks  │
   └────────┘└────────┘  └────────┘  └────────┘
```

- **Driver** — runs `main()`, holds the `SparkSession`, builds the logical/physical
  plan, schedules **stages → tasks**, and collects results.
- **Cluster manager** — provisions executors (Standalone, YARN, Kubernetes, Mesos,
  or `local[*]` for a single machine using N threads).
- **Executors** — run tasks, cache data, and report back.
- **Job → Stages → Tasks** — every *action* triggers a **job**; the DAG is split
  into **stages** at shuffle boundaries; each stage runs one **task per partition**.

### Lazy evaluation
**Transformations** (`map`, `filter`, `select`, `join`, …) are lazy — they only
build the plan. **Actions** (`count`, `collect`, `show`, `write`, …) trigger
execution. This lets Catalyst optimize the whole plan before running anything.

### Narrow vs wide dependencies
- **Narrow** (`map`, `filter`, `union`) — each input partition feeds one output
  partition; no data movement.
- **Wide** (`groupBy`, `join`, `repartition`, `distinct`) — require a **shuffle**:
  data is redistributed across the network. Shuffles define stage boundaries and
  are the main performance cost.

---

## 3. The two core abstractions

### 3.1 RDD (Resilient Distributed Dataset)
The original low-level API: an immutable, partitioned collection with lineage.
Resilient because lost partitions are recomputed from lineage. You use RDDs for
fine-grained control, custom partitioning, or unstructured data. Operations:
- *Transformations*: `map`, `flatMap`, `filter`, `reduceByKey`, `groupByKey`,
  `mapPartitions`, `sortBy`, `union`, `distinct`, `join`.
- *Actions*: `collect`, `count`, `take`, `reduce`, `fold`, `aggregate`,
  `saveAsTextFile`, `foreach`.

### 3.2 DataFrame / Dataset
A distributed table with a **schema**. This is the recommended API: it goes
through **Catalyst** (query optimizer) and **Tungsten** (whole-stage codegen,
off-heap memory), so it is far faster than raw RDDs and works identically across
Python/Scala/SQL. In Python there is no typed `Dataset[T]` — you use DataFrames.

---

## 4. Spark SQL & the DataFrame API

- **Reading/writing**: `spark.read.format(...)` and `df.write...` for CSV, JSON,
  Parquet, ORC, Avro, JDBC, Delta, plus partitioned & bucketed output.
- **Schema**: define explicitly with `StructType`/`StructField` or infer it.
  Includes nested `StructType`, `ArrayType`, `MapType`.
- **Column expressions**: `col`, `lit`, arithmetic, `when/otherwise`, string &
  date functions, `cast`, `alias`.
- **Relational ops**: `select`, `filter/where`, `withColumn`, `drop`, `distinct`,
  `orderBy`, `limit`.
- **Aggregations**: `groupBy().agg(...)`, `count`, `sum`, `avg`, `min`, `max`,
  `collect_list`, `approx_count_distinct`, `pivot`, `cube`, `rollup`.
- **Joins**: inner, left/right/full outer, left semi, left anti, cross; plus
  **broadcast** joins for small tables.
- **Window functions**: `row_number`, `rank`, `dense_rank`, `lag`, `lead`,
  running sums and moving averages over `Window.partitionBy().orderBy()`.
- **Set ops**: `union`, `unionByName`, `intersect`, `except`.
- **SQL**: register temp views (`createOrReplaceTempView`) and run `spark.sql(...)`.
- **Catalog API**: `spark.catalog` to list/inspect databases, tables, functions.
- **UDFs**: Python `udf`, and Arrow-accelerated **pandas UDFs**
  (`@pandas_udf`, scalar / grouped-map / grouped-agg). Prefer built-ins first.
- **Null handling**: `na.fill`, `na.drop`, `coalesce`, `isNull`, `nvl`.

### Catalyst & optimization
Catalyst transforms: parsed → analyzed → optimized logical plan → physical plans
→ cost-based selection → Tungsten codegen. Key features:
- **Predicate / projection pushdown** to the data source.
- **Adaptive Query Execution (AQE)** — re-optimizes at runtime: coalesces shuffle
  partitions, switches join strategies, handles skew.
- **Partition pruning** & **dynamic partition pruning**.

---

## 5. Performance & tuning

- **Caching / persistence**: `cache()` / `persist(StorageLevel)` to reuse a
  DataFrame across actions; `unpersist()` to free it.
- **Partitioning**: `repartition(n)` (full shuffle, even sizing),
  `coalesce(n)` (no shuffle, shrink only), `repartitionByRange`,
  `partitionBy` on write.
- **Broadcast variables** & **broadcast joins**: ship a small dataset to every
  executor instead of shuffling a large one.
- **Accumulators**: write-only shared counters for metrics/debugging.
- **Shuffle tuning**: `spark.sql.shuffle.partitions`, AQE, salting for skew.
- **File layout**: columnar formats (Parquet/ORC), compression, partition &
  bucket design, avoiding many tiny files.
- **`explain(True)`** to read the logical/physical plan.

---

## 6. Structured Streaming

A streaming DataFrame is an unbounded table that grows over time. Same API as
batch. Concepts:
- **Sources**: files, Kafka, socket, rate.
- **Sinks**: console, files, Kafka, `foreachBatch`, memory.
- **Triggers**: micro-batch (default), fixed interval, `availableNow`, continuous.
- **Output modes**: `append`, `update`, `complete`.
- **Event-time windows** + **watermarks** for late data.
- **Stateful ops**: aggregations, deduplication, stream-stream joins.
- **Checkpointing** for exactly-once fault tolerance.

---

## 7. MLlib (DataFrame-based ML)

Pipeline abstractions:
- **Transformer** — `transform()` a DataFrame (e.g. `Tokenizer`, `VectorAssembler`,
  a fitted model).
- **Estimator** — `fit()` produces a model (e.g. `LogisticRegression`,
  `RandomForestClassifier`, `KMeans`, `ALS`).
- **Pipeline** — chains stages so the same steps apply to train & serve.
- **Feature tooling** — `StringIndexer`, `OneHotEncoder`, `StandardScaler`,
  `VectorAssembler`, `Tokenizer`, `HashingTF`.
- **Tuning** — `CrossValidator`, `TrainValidationSplit`, `ParamGridBuilder`.
- **Evaluation** — classification / regression / clustering evaluators.

---

## 8. The example project

[`example-project/`](./example-project) implements all of the above as small,
focused, tested modules. See its
[README](./example-project/README.md) for the module map and how to run it.
