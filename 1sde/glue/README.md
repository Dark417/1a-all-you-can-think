# AWS Glue & the Glue Data Catalog

This directory explains the **AWS Glue Data Catalog** and provides a runnable
example Python project (`example-project/`) that manages catalog objects with
`boto3` and runs a PySpark-based Glue ETL job.

---

## 1. What is AWS Glue?

AWS Glue is a serverless data-integration service. You do not manage servers;
you submit jobs and AWS provisions Spark (or Python shell) workers on demand.
Glue has several components:

| Component            | Purpose                                                                 |
|----------------------|-------------------------------------------------------------------------|
| **Data Catalog**     | Central metadata store (databases, tables, schemas, partitions).        |
| **Crawlers**         | Scan data stores, infer schema, and populate the catalog automatically. |
| **ETL Jobs**         | Spark (Scala/PySpark) or Python-shell jobs that transform data.         |
| **Triggers**         | Schedule or event-start jobs (cron, on-demand, job-completion).         |
| **Workflows**        | Orchestrate multiple crawlers/jobs/triggers as a DAG.                    |
| **Glue Studio**      | Visual, no-code/low-code job authoring.                                 |
| **DataBrew**         | Visual data preparation/profiling.                                      |
| **Schema Registry**  | Versioned schemas for streaming (Avro/JSON/Protobuf).                    |
| **Interactive Sessions** | Notebook-style, pay-per-second Spark development.                    |

---

## 2. The Glue Data Catalog in depth

The Data Catalog is a **persistent, Hive-Metastore-compatible metadata
repository**. It does *not* store your data — it stores metadata that describes
where the data lives (S3, RDBMS, DynamoDB, …), how it is formatted, and what its
schema is. One catalog exists **per AWS account, per region**.

### 2.1 Object hierarchy

```
Catalog (account + region)
└── Database                     ← logical namespace, e.g. "sales_db"
    └── Table                    ← schema + storage descriptor
        ├── Columns              ← name + type + comment
        ├── StorageDescriptor    ← location, input/output format, SerDe
        ├── PartitionKeys        ← columns used to partition (e.g. year, month)
        └── Partitions           ← one entry per partition value combination
```

### 2.2 What a *Table* actually contains

A catalog table is metadata only. Its key pieces:

- **Columns** — the schema: `[{Name, Type, Comment}]`. Types are Hive types
  (`string`, `int`, `bigint`, `double`, `boolean`, `timestamp`,
  `array<…>`, `struct<…>`, `map<…,…>`).
- **StorageDescriptor**:
  - `Location` — e.g. `s3://my-bucket/sales/`
  - `InputFormat` / `OutputFormat` — Hadoop format classes
  - `SerdeInfo` — the SerDe (serializer/deserializer) and its parameters
  - `Columns` — same schema, attached to the descriptor
- **PartitionKeys** — columns *not* stored in the files but encoded in the S3
  path (Hive-style `year=2024/month=01/`).
- **TableType** — `EXTERNAL_TABLE` (most common) or `VIRTUAL_VIEW`.
- **Parameters** — free-form key/values (`classification=parquet`,
  `compressionType=snappy`, record counts, etc.).

### 2.3 Partitions — why they matter

For large S3 datasets you partition by columns like date or region. Each
partition is a separate catalog entry pointing at a sub-prefix:

```
s3://my-bucket/sales/year=2024/month=01/   ← partition (2024, 01)
s3://my-bucket/sales/year=2024/month=02/   ← partition (2024, 02)
```

Query engines (Athena, Redshift Spectrum, Spark) use partitions for **partition
pruning** — only reading the prefixes that match a `WHERE year=2024` filter.
This dramatically reduces scanned bytes (and cost).

You add partitions by: (a) running a crawler, (b) `MSCK REPAIR TABLE` /
`ALTER TABLE ADD PARTITION` in Athena, (c) `boto3` `batch_create_partition`, or
(d) **partition projection** (compute partitions from a pattern, no catalog
entries needed).

### 2.4 Crawlers

A crawler connects to a data store, walks the objects, infers schema with
**classifiers** (built-in for JSON/CSV/Parquet/ORC/Avro/XML or custom Grok/regex),
groups compatible files into tables, and writes/updates the catalog. Crawlers
can run on schedule and detect new partitions or schema drift.

### 2.5 Who consumes the catalog?

The catalog is the *single source of truth* across the analytics stack:

- **Amazon Athena** — serverless SQL directly over S3 using catalog tables.
- **Redshift Spectrum** — query S3 from Redshift via external schemas.
- **EMR / Spark / Hive / Presto / Trino** — use it as the Hive Metastore.
- **Glue ETL jobs** — read with `glueContext.create_dynamic_frame.from_catalog`.
- **Lake Formation** — fine-grained (row/column) governance on catalog objects.

### 2.6 DynamicFrame vs DataFrame

Glue adds the **DynamicFrame**, a Spark DataFrame variant that:

- Needs no up-front schema; it tracks per-record schema and **choice types**
  for messy/evolving data.
- Has ETL-specific transforms: `ResolveChoice`, `ApplyMapping`, `Relationalize`,
  `DropNullFields`, `Unbox`, `Filter`.
- Converts to/from a normal DataFrame via `.toDF()` / `DynamicFrame.fromDF()`.

Use DataFrames for rich SQL/analytics; use DynamicFrames for ingest, schema
resolution, and catalog/bookmark integration.

### 2.7 Job bookmarks

Glue **job bookmarks** persist state between runs so a job only processes
*new* data (incremental ETL), tracked by primary key / timestamp / file
modification.

---

## 3. The example project

See [`example-project/`](./example-project) for runnable code that:

1. Creates a Glue **database**.
2. Creates a partitioned **table** with an explicit schema.
3. Adds **partitions** in batch.
4. Lists / reads back catalog metadata.
5. Defines a **Glue ETL job** (PySpark + DynamicFrame) reading from the catalog,
   transforming, and writing partitioned Parquet back to S3 + the catalog.
6. Includes a **local pytest** using `moto` to mock AWS — no AWS account needed
   to run the tests.

Start with [`example-project/README.md`](./example-project/README.md).
