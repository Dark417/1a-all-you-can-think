# Architecture — Deep Dive

This document explains the Databricks Lakehouse architecture and exactly how each
piece is realised in this demo. Where it matters, it calls out what is **real**
(identical to production) versus **emulated** (a faithful local stand-in).

---

## 1. The Lakehouse paradigm

Historically you had two systems:

- a **data warehouse** — fast SQL, ACID transactions, governance, but
  proprietary storage and expensive;
- a **data lake** — cheap open object storage (S3/GCS/ADLS) holding raw files,
  but no transactions, no schema enforcement, and a "small-file"/consistency mess.

The **Lakehouse** unifies them: keep data in cheap open object storage **but**
add a transactional table format on top that gives warehouse semantics. On
Databricks that format is **Delta Lake**. You get ACID, time travel, schema
enforcement/evolution, `MERGE`, and good performance — directly over open files
that any engine can read.

> **In this demo:** the Lakehouse storage is **real**. `delta-rs` writes genuine
> Delta tables to `DELTA_DIR/<catalog>/<schema>/<table>`. DuckDB (our compute)
> reads them back via the `delta` extension. The format is production-identical.

---

## 2. Delta Lake internals

A Delta table on disk is just a directory:

```
main/sales/customers/
├── _delta_log/
│   ├── 00000000000000000000.json   # commit 0: metaData + protocol + add files
│   ├── 00000000000000000001.json   # commit 1: add/remove file actions
│   └── ...                         # (periodic .checkpoint.parquet for speed)
├── part-00000-....parquet          # immutable Parquet data files
└── part-00001-....parquet
```

### The transaction log (`_delta_log`)

The log is the source of truth. Each commit is an **atomic**, numbered JSON file
listing *actions*: `metaData` (schema), `protocol` (reader/writer versions),
`add` (a new Parquet file with stats), `remove` (tombstone a file). The current
table state = replaying all commits. Inspect it here with:

```
GET /delta/{fqn}/history          # one entry per commit, with operation + metrics
GET /delta/{fqn}/describe-detail  # current version, file count, total size, schema
```

### ACID & optimistic concurrency

Writers stage Parquet files, then attempt to commit by writing the next numbered
log entry. The commit is the atomic step (a single put/rename). If two writers
race for the same version number, one wins and the other retries against the new
snapshot — **optimistic concurrency control**. delta-rs implements this exactly,
so the demo's commits are genuinely ACID.

### Data files = Parquet

Data lives in immutable, columnar Parquet files, each carrying per-column
min/max statistics in the log's `add` action. Queries use those stats for **data
skipping** (don't open files that can't match a predicate) — the open-format
analogue of Snowflake's micro-partition pruning.

### Time travel

Because old files are only *tombstoned* (not deleted) until `VACUUM`, any prior
version is reconstructable. Databricks: `SELECT * FROM t VERSION AS OF 3`. Here:

```
GET /delta/{fqn}/data?version=3
```

The demo proves this is real: in `demo.py`, version 1 of `customers` has 3 rows
while the latest version (after MERGE/UPDATE/DELETE + a schema-evolving append)
has 4 rows and an extra column.

### Schema enforcement & evolution

Writes that don't match the schema are rejected (enforcement). Opt-in evolution
(`schema_mode="merge"`) adds new columns:

```
POST /delta/{fqn}/append   { "rows": [...], "evolve_schema": true }
```

### OPTIMIZE, Z-ORDER, VACUUM, liquid clustering

- **OPTIMIZE** (`/delta/{fqn}/optimize`) — bin-packs many small files into fewer
  large ones (fixes the small-file problem streaming/MERGE create). **Real**:
  delta-rs `optimize.compact()`.
- **Z-ORDER** (`/delta/{fqn}/zorder`) — reorders data along multiple columns so
  related values co-locate, improving data skipping. **Real**:
  `optimize.z_order(cols)`.
- **VACUUM** (`/delta/{fqn}/vacuum`) — deletes tombstoned files older than the
  retention window. Defaults to **dry-run** here so time travel is preserved.
- **Liquid clustering** — Databricks' newer alternative to partitioning + Z-ORDER
  that adapts clustering automatically. Mentioned for completeness; this demo
  uses partitioning + Z-ORDER (delta-rs does not yet expose liquid clustering).

---

## 3. The Databricks compute model

### Control plane vs data plane

- **Control plane** (managed by Databricks): the web app/APIs, job scheduler,
  Unity Catalog metastore, MLflow, query history, cluster manager. *No customer
  data passes through it.*
- **Data plane** (in **your** cloud account): the clusters (VMs) and the object
  storage holding Delta tables. Compute reads/writes your data directly.

> **In this demo:** MongoDB + FastAPI play the control plane (metadata, jobs,
> registry, history); delta-rs + DuckDB play the data plane (data + compute).

### Clusters, Photon, serverless, DBUs

- **All-purpose clusters** — interactive (notebooks, ad-hoc).
- **Job clusters** — created for one job run, torn down after (cheaper).
- **SQL warehouses** — compute for Databricks SQL / BI.
- **Photon** — Databricks' vectorised C++ execution engine; big speedups for SQL.
- **Serverless** — Databricks-managed compute that starts in seconds (no VM
  management).
- **DBUs (Databricks Units)** — the billing unit; you're charged DBUs/second
  while compute runs, scaled by size and worker count (**autoscaling**).

> **In this demo (`core/engine.py`, `routers/clusters.py`):** a cluster is a
> MongoDB object with a size, state (`RUNNING`/`TERMINATED`), and autoscaling
> `min_workers`/`max_workers`/`current_workers`. Its size sets DuckDB's thread
> budget (more workers ≈ more threads). Every query meters **DBUs** =
> `rate(size) × elapsed_seconds × active_workers`, recorded on the cluster and in
> query history. DuckDB is our always-on "Photon". A query against a terminated
> cluster **auto-starts** it, like a real cluster waking up.

---

## 4. Unity Catalog

Unity Catalog is the unified governance layer:

- **Metastore** — one per region; the top-level container of all metadata.
- **Three-level namespace** — `catalog.schema.table` (the big upgrade over the
  2-level Hive metastore). A catalog groups schemas; a schema groups tables.
- **Securables & grants** — privileges (`SELECT`, `MODIFY`, `USE_SCHEMA`,
  `USE_CATALOG`, `ALL_PRIVILEGES`, …) granted to **principals** (users/groups) on
  securables. Grants on a parent **cascade** to children: to read
  `main.sales.customers` a principal needs `USE_CATALOG` on `main`, `USE_SCHEMA`
  on `main.sales`, and `SELECT` on the table.
- **Lineage** — Unity Catalog automatically captures table- and column-level
  lineage across notebooks/jobs/pipelines.
- **Audit** — every action is logged.

> **In this demo (`routers/catalog.py`, `core/lineage.py`):** catalogs, schemas
> and table registrations live in MongoDB. Tables are addressed as
> `catalog.schema.table` everywhere and stored on disk under the matching path.
> `POST /catalog/grants` records grants; `GET /catalog/effective-privileges`
> unions the catalog/schema/table-level grants for a principal to decide
> `can_select`. Lineage edges are recorded automatically by the medallion, DLT
> and Auto Loader routers and exposed at `GET /governance/lineage`.

---

## 5. Medallion architecture

A convention for organising Lakehouse data into progressively refined tiers,
each a Delta table:

- **Bronze** — raw, append-only, as-ingested (full fidelity, replayable).
- **Silver** — cleaned, de-duplicated, conformed, validated (the trustworthy
  source of truth most consumers use).
- **Gold** — business-level aggregates / marts for BI and ML features.

> **In this demo (`routers/medallion.py`):** `POST /medallion/bronze` appends raw
> rows; `/silver` reads bronze, drops null-key rows and de-duplicates with polars,
> writing a new Delta table; `/gold` aggregates silver. Each hop records a
> lineage edge, so `GET /governance/lineage/{gold}/upstream` returns the full
> bronze→silver→gold chain.

---

## 6. Structured Streaming & Auto Loader

- **Structured Streaming** — Spark's stream processing API; a streaming query is
  an incremental computation that periodically processes new input as
  *micro-batches* and commits results transactionally to a Delta sink. A
  **checkpoint** stores progress (offsets) so it can resume exactly-once.
- **Auto Loader** (`cloudFiles`) — the recommended way to ingest files landing in
  cloud storage incrementally and idempotently. It tracks which files it has
  already seen so each file is processed exactly once. `trigger(availableNow=True)`
  (or the older `once=True`) processes everything currently available, then stops
  — "batch-flavoured streaming".

> **In this demo (`routers/autoloader.py`):** a stream watches a subdirectory of
> `STAGE_DIR`; its **checkpoint** is the set of already-processed filenames stored
> in MongoDB. `POST /autoloader/{n}/trigger` reads only *new* files, appends them
> to a bronze Delta table (with schema evolution), and advances the offset.
> Re-triggering with no new files is a no-op — **exactly-once**.

---

## 7. Delta Live Tables (DLT)

DLT is **declarative** ETL: you define tables with `@dlt.table` functions and
declarative **expectations**; DLT infers the dependency DAG, materialises each
table, and enforces data quality. Expectation actions:

- `@dlt.expect` → **WARN**: keep violating rows, record the metric.
- `@dlt.expect_or_drop` → **DROP**: quarantine (drop) violating rows.
- `@dlt.expect_or_fail` → **FAIL**: abort the update on any violation.

> **In this demo (`routers/dlt.py`):** a pipeline is a list of steps
> (`name` + `query` + `depends_on` + `expectations`). `POST /dlt/{n}/run`
> topologically sorts the steps, runs each on DuckDB over the upstream Delta
> tables, evaluates each expectation's boolean SQL constraint per row, applies
> WARN/DROP/FAIL, writes the result as a Delta table, records lineage, and returns
> a per-step, per-expectation report (rows passed / failed / quarantined).

---

## 8. Workflows (Jobs)

Databricks **Workflows** orchestrate **jobs** of multiple **tasks** with
`depends_on` edges (a DAG). Tasks can be notebooks, SQL, JARs, dbt, etc., run on
shared or per-task job clusters, triggered on a schedule (cron) or on demand,
with retries and per-task run history.

> **In this demo (`routers/jobs.py`):** a job owns multiple tasks with
> `depends_on`. `POST /jobs/{n}/run` topo-sorts and runs the tasks on a cluster;
> if an upstream task fails, downstream tasks are `SKIPPED`. Schedules use
> **APScheduler**. `GET /jobs/{n}/runs` returns per-task status history.

---

## 9. MLflow & the Model Registry

Databricks bundles managed **MLflow** for the ML lifecycle:

- **Tracking** — log experiments, runs, params, metrics, tags, artifacts.
- **Model Registry** — register models, version them, and transition versions
  through **stages** (`Staging` → `Production` → `Archived`).

> **In this demo (`routers/mlflow_router.py`):** this is **real MLflow** against a
> local **sqlite** tracking backend under `MLRUNS_DIR` (the file store is in
> maintenance mode in MLflow 3.x). To keep dependencies light we log a trivial
> `pyfunc` model (no sklearn) so registration and stage transitions genuinely
> work — `GET /mlflow/models` lists the registered model and its current stage.

---

## 10. Databricks SQL (DBSQL)

Databricks SQL gives BI-style SQL on the Lakehouse via **SQL warehouses**
(Photon compute), with result caching, query history, and dashboards — all over
the same Delta tables, governed by Unity Catalog.

> **In this demo (`routers/sql.py`, `core/engine.py`):** `POST /sql` runs SQL on
> a cluster. Delta tables are exposed to DuckDB as views over
> `delta_scan('<path>')` (zero-copy, reads the live committed state). Read-only
> queries are served from a **result cache** on repeat; every query meters DBUs
> and is appended to query history (the audit trail).

---

## What is real vs emulated — summary

| Capability | Status |
|---|---|
| Delta table format (`_delta_log` + Parquet) | **Real** (delta-rs; openable by Databricks) |
| ACID commits, optimistic concurrency | **Real** |
| MERGE / UPDATE / DELETE | **Real** |
| Time travel / history | **Real** |
| Schema evolution | **Real** |
| OPTIMIZE / Z-ORDER / VACUUM | **Real** |
| SQL query engine | **Real** (DuckDB; Photon stand-in) |
| MLflow tracking + registry | **Real** (local sqlite) |
| Clusters, DBUs, autoscaling, Photon | **Emulated** (logical objects + metering) |
| Unity Catalog metastore, grants, lineage | **Emulated** (MongoDB) |
| Auto Loader, DLT, Workflows, Notebooks | **Emulated** orchestration over real Delta |
