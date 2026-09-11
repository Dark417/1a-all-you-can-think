# Snowflake Architecture — A Deep Dive

This document explains how Snowflake actually works, then shows precisely how
each concept is emulated by the local demo in this repository. The goal is that
after reading it you understand *why* Snowflake is built the way it is — not
just the API surface.

---

## 1. The core idea: a multi-cluster, shared-data architecture

Traditional data platforms come in two shapes:

- **Shared-disk** (e.g. classic Oracle RAC): every compute node sees one shared
  storage pool but they must coordinate over a shared cache → contention.
- **Shared-nothing** (e.g. classic Hadoop/MPP like Teradata, Redshift):
  data is *partitioned across* the compute nodes. Storage and compute are
  welded together, so to add compute you must reshuffle data, and concurrent
  workloads fight over the same fixed cluster.

Snowflake invented a third shape: **multi-cluster, shared-data**. There is a
single, central copy of the data in cloud object storage, and *any number of
independent compute clusters* ("virtual warehouses") operate on it
simultaneously. This is the source of Snowflake's headline properties:

- **Independent elastic scaling** of storage and compute.
- **Workload isolation**: ETL, BI dashboards, and data science each get their
  own warehouse; one cannot slow another down.
- **Pay-per-second compute** that can be suspended to zero.

```
                    ┌──────────────────────────────────────────┐
                    │            CLOUD SERVICES LAYER            │
                    │  auth · RBAC · metadata · optimizer ·      │
                    │  transaction mgr · result cache · sharing  │
                    └──────────────────────────────────────────┘
                                     │ (brains)
        ┌────────────────┬───────────┴───────────┬────────────────┐
        ▼                ▼                        ▼                ▼
 ┌────────────┐  ┌────────────┐           ┌────────────┐   ┌────────────┐
 │ Warehouse  │  │ Warehouse  │   ...     │ Warehouse  │   │ Warehouse  │   QUERY
 │   (ETL)    │  │   (BI)     │           │   (DS)     │   │  (ad-hoc)  │   PROCESSING
 │  X-SMALL   │  │  X-LARGE   │           │  MEDIUM    │   │  SUSPENDED │   (muscle)
 └────────────┘  └────────────┘           └────────────┘   └────────────┘
        │                │                        │                │
        └────────────────┴───────────┬───────────┴────────────────┘
                                      ▼
                    ┌──────────────────────────────────────────┐
                    │              STORAGE LAYER                 │
                    │  immutable, columnar MICRO-PARTITIONS on   │
                    │  cloud object storage (S3 / GCS / Azure)   │
                    └──────────────────────────────────────────┘
```

The three layers scale and are billed **independently**. That separation is the
whole game.

---

## 2. Layer 1 — Centralized Storage (micro-partitions)

When you load data, Snowflake reorganizes it into **micro-partitions**:

- Contiguous units of storage, ~50–500 MB of *uncompressed* data
  (≈16 MB compressed), each holding a subset of **rows**.
- Stored **columnar** within the partition (like Parquet), so a query only
  reads the columns it needs.
- **Immutable**. An UPDATE/DELETE never edits a partition in place — it writes
  *new* partitions and marks old ones as no longer part of the current table
  version. This immutability is what makes Time Travel, Cloning, and Streams
  possible (see below).
- Each micro-partition carries **metadata**: the min/max value of every column,
  distinct counts, null counts, etc.

### Pruning
Because every partition advertises its column min/max ranges, the optimizer can
**prune** — skip partitions that cannot possibly match a `WHERE` clause —
without reading them. This is the columnar equivalent of an index, but
automatic and maintenance-free. Good natural clustering (data loaded roughly
sorted by a frequently filtered column) makes pruning dramatically effective.

### Clustering keys
For very large tables you can define a **clustering key**; Snowflake's automatic
clustering service reorganizes micro-partitions in the background to keep
related rows co-located, improving pruning.

> **In this demo:** `GET /tables/{fqn}/micro-partitions` exports a table to
> Parquet with small row groups and reads back the **row-group min/max
> statistics** — the exact mechanism Snowflake uses for pruning, made tangible.
> The single DuckDB database file plays the role of centralized storage.

---

## 3. Layer 2 — Query Processing (Virtual Warehouses)

A **virtual warehouse** is a cluster of compute (MPP) nodes that Snowflake
provisions on demand. Key facts:

- **Sizes** go X-SMALL, SMALL, MEDIUM, ... each step **doubling** the node
  count and therefore the **credit/hour** rate (XS = 1, S = 2, M = 4, ...).
- **Elasticity**: resize at any time; the new size applies to subsequent
  queries — no data movement, because the data lives in the storage layer, not
  on the warehouse.
- **Auto-suspend / auto-resume**: an idle warehouse suspends (billing stops);
  the next query resumes it automatically (typically with a 60-second minimum
  billing on resume).
- **Local cache**: each warehouse keeps a local SSD cache of micro-partitions
  it has read, so repeated queries on warm data are fast. Resizing or
  suspending clears this cache.
- **Multi-cluster warehouses** (Enterprise+): a warehouse can automatically add
  *more clusters of the same size* to handle concurrency spikes (many users),
  as opposed to resizing (a bigger single cluster for one heavy query).

The mental model: **resize for query *size*, multi-cluster for query
*concurrency*.**

> **In this demo:** each warehouse is a document in MongoDB with a `size`,
> `state`, and accumulating `credits_used`. `app/core/engine.py` applies a
> per-size **DuckDB thread budget** (more threads = "bigger" warehouse) and
> **meters credits** against wall-clock execution time using the real
> XS=1/S=2/M=4 ratios. Suspended warehouses **auto-resume** on the next query,
> exactly like Snowflake. Endpoints: `POST /warehouses`, `.../resize`,
> `.../suspend`, `.../resume`, `.../usage`.

---

## 4. Layer 3 — Cloud Services (the brains)

A collection of always-on, multi-tenant services that coordinate everything.
This layer is "free" up to ~10% of daily compute usage. It handles:

- **Authentication & access control** (RBAC — see §8).
- **Infrastructure & metadata management**: the catalog of all databases,
  schemas, tables, and crucially the **micro-partition metadata** used for
  pruning. Metadata operations like `SELECT COUNT(*)` or `MIN/MAX` can often be
  answered from metadata alone — *without* spinning up a warehouse.
- **Query parsing & optimization**: a cost-based optimizer that uses partition
  statistics to build the plan and decide pruning.
- **Transaction management**: ACID via snapshot isolation over immutable
  partitions.
- **The Result Cache**: identical queries return cached results for **24 hours**
  with **zero** warehouse compute (as long as underlying data hasn't changed).
- **Secure Data Sharing** metadata (see §11).

> **In this demo:** the MongoDB catalog + FastAPI routers *are* the cloud
> services layer. The **result cache** is implemented in `engine.py` (identical
> read-only SQL → cached rows, `credits_used = 0`, `from_cache = true`).
> `QUERY_HISTORY` is recorded for every statement
> (`GET /governance/query-history`).

---

## 5. The object namespace

Snowflake organizes objects in a three-level namespace:

```
ACCOUNT
└── DATABASE                e.g. ANALYTICS
    └── SCHEMA              e.g. SALES
        ├── TABLE / VIEW
        ├── STAGE
        ├── STREAM / TASK
        ├── FILE FORMAT
        └── FUNCTION / PROCEDURE
```

Fully-qualified name = `DATABASE.SCHEMA.OBJECT`.

> **In this demo:** DuckDB only has two levels (schema.table), so we encode the
> Snowflake `DATABASE.SCHEMA` into a single physical DuckDB schema named
> `DATABASE$SCHEMA` (see `app/core/naming.py`). All three Snowflake levels
> survive round-trips.

---

## 6. Semi-structured data (VARIANT)

Snowflake natively stores JSON/Avro/Parquet/XML in a **VARIANT** column. Under
the hood it shreds the semi-structured data into a columnar representation, so
querying nested paths (`col:a.b[0]`) is fast and can even be pruned. This is why
Snowflake is comfortable as both a warehouse and a semi-structured data lake.

> **In this demo:** `VARIANT` maps to DuckDB's `JSON` type. You can insert
> nested objects via `POST /tables/{fqn}/insert` and query paths with
> `PROFILE->>'tier'` through `POST /sql`.

---

## 7. Continuous data engineering: Stages, Snowpipe, Streams, Tasks

These four objects compose into declarative pipelines.

- **Stage**: a named location for files. *Internal* stages live in Snowflake-
  managed storage; *external* stages point at your own S3/GCS/Azure bucket.
- **`COPY INTO`**: the bulk loader. It parses staged files according to a
  **File Format** and appends rows to a table. Snowflake tracks load history so
  the same file isn't loaded twice.
- **Snowpipe**: event-driven, *continuous* micro-batch loading. A **pipe**
  wraps a `COPY INTO`; when a new file lands (via cloud notification or REST),
  Snowpipe ingests it automatically using Snowflake-managed serverless compute.
- **Stream**: a **change-tracking** object (CDC). It records an offset on a
  table and, when read, returns the rows inserted/updated/deleted since that
  offset plus metadata columns (`METADATA$ACTION`, `METADATA$ISUPDATE`).
  Consuming the stream in a DML statement advances the offset transactionally.
  Streams exist *because* storage is immutable — a stream is just a bookmark
  into the version history.
- **Task**: a scheduled unit of SQL. A **root** task runs on a cron/interval
  schedule; **child** tasks run `AFTER` a parent, forming a **DAG**. The classic
  pattern is `Stream + Task`: a task wakes on a schedule, checks
  `SYSTEM$STREAM_HAS_DATA`, and if there are changes, MERGEs them downstream.

> **In this demo:**
> - `POST /stages`, `PUT /stages/{stage}/files`, `POST /stages/copy-into` for
>   staging + bulk load (CSV/JSON/Parquet via DuckDB readers).
> - `POST /stages/pipes` + uploading a matching file triggers **auto-ingest**
>   (`_maybe_trigger_pipes`).
> - `POST /streams` then mutating the table → `GET /streams/{name}` returns the
>   diff with `METADATA$ACTION`; `POST /streams/{name}/consume` advances the
>   offset. Changes are derived by **diffing time-travel snapshots**.
> - `POST /tasks` with `schedule_seconds` (root) or `after` (child) builds a DAG
>   run by APScheduler; `POST /tasks/{name}/run` executes the whole subtree.

---

## 8. Time Travel & Zero-Copy Cloning

Both fall straight out of immutable micro-partitions + metadata versioning.

- **Time Travel**: every table change produces a new *version*; old versions'
  micro-partitions still physically exist for the **retention period**
  (1 day Standard, up to 90 days Enterprise). So you can:
  - `SELECT ... AT (TIMESTAMP => ...)` / `BEFORE (STATEMENT => ...)` —
    query the past.
  - `UNDROP TABLE` — recover a dropped object.
  - Recover from a bad `UPDATE`/`DELETE` by restoring a prior version.
  - After retention, partitions move to **Fail-safe** (7 days, Snowflake-only
    recovery).
- **Zero-Copy Cloning**: `CREATE TABLE ... CLONE` (also schemas and whole
  databases) creates a new object that **references the same micro-partitions**
  — no data is copied. Storage diverges only when one side is modified
  (**copy-on-write**). This makes instant, cheap dev/test/QA environments from
  production data.

> **In this demo:** `app/core/history.py` snapshots a table's full row set into
> MongoDB on every mutation (`version`, `timestamp`, `change_type`).
> `GET /time-travel/{fqn}/history`, `.../at?version=` or `?before_timestamp=`,
> and `POST /time-travel/{fqn}/restore` implement Time Travel.
> `POST /time-travel/clone` performs the clone (CTAS in DuckDB = the
> copy-on-write moment).

---

## 9. Security & RBAC

Snowflake access control is **role-based and discretionary**:

- Privileges (`SELECT`, `INSERT`, `USAGE`, `OWNERSHIP`, ...) are granted to
  **roles**, never directly to users.
- Roles are granted to **users** and to **other roles**, forming a **hierarchy**.
  A user's effective privileges = the union over their active role and every
  role beneath it.
- System roles: `ACCOUNTADMIN` (top) → `SECURITYADMIN` / `SYSADMIN` → custom
  roles → `PUBLIC` (everyone).
- Plus column/row-level security: **masking policies** and **row-access
  policies**.

> **In this demo:** `POST /rbac/bootstrap` creates the system roles;
> `POST /rbac/roles`, `/users`, `/grants`, `/grants/role` build the graph;
> `GET /rbac/roles/{role}/effective-privileges` **walks the hierarchy** and
> unions privileges — exactly how Snowflake authorizes an action; `GET
> /rbac/check` answers "is this allowed?".

---

## 10. Extensibility: UDFs & Stored Procedures

- **SQL UDFs**: an expression inlined into queries.
- **Python/Java/Scala UDFs** (Snowpark): run user code in a secure sandbox next
  to the data.
- **Stored Procedures**: procedural control flow (loops, branching, transaction
  control) in SQL/JavaScript/Python.

> **In this demo:** `POST /functions` registers SQL UDFs (DuckDB macros) and
> **real Python UDFs** (registered with DuckDB so they execute inside SQL).
> `POST /functions/{name}/call` invokes them.

---

## 11. Governance & sharing

- **Secure Data Sharing**: share live, read-only access to objects with other
  Snowflake accounts **without copying data** — the consumer queries your
  micro-partitions directly (you pay storage, they pay their own compute). The
  **Marketplace** is built on this.
- **Resource Monitors**: set credit quotas per warehouse/account with
  notify/suspend actions to control spend.
- **Account/Object usage views** (`SNOWFLAKE.ACCOUNT_USAGE`, `QUERY_HISTORY`):
  observability over usage, cost, and access.

> **In this demo:** `POST /governance/shares` (live, no-copy share),
> `POST /governance/resource-monitors` + `.../evaluate` (quota enforcement that
> actually suspends warehouses on breach), `GET /governance/query-history`,
> and `DELETE /governance/result-cache`.

---

## 12. What the demo deliberately simplifies

This is a teaching emulator, not a Snowflake reimplementation. Notable
simplifications:

| Aspect | Real Snowflake | This demo |
|---|---|---|
| Storage | Distributed columnar micro-partitions on object storage | One DuckDB file; Parquet row groups illustrate partitions |
| Compute | Real MPP clusters, per-warehouse SSD cache | DuckDB threads + simulated credit metering |
| Concurrency | Multi-cluster warehouses, true MVCC | Single DuckDB connection under a lock |
| Time Travel | Pointer flips over retained partitions (no row copy) | Full-row snapshots in MongoDB |
| Clone | Copy-on-write partition references | `CREATE TABLE AS SELECT` (eager copy) |
| Load history | Files never double-loaded | `COPY INTO` will re-load if you re-run it |
| Security | Encryption, network policies, masking/row policies | RBAC graph + authorization checks only |

These trade-offs keep the project **100% local and dependency-light** while
still demonstrating the *behavior and intent* of every feature.

➡️ Continue with **[PIPELINES.md](PIPELINES.md)** to build an end-to-end
pipeline, and **[CLOUD_PROMOTION.md](CLOUD_PROMOTION.md)** to take it to real
Snowflake on AWS or GCP.
