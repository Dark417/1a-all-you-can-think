# Building Pipelines

How to build the four canonical Databricks pipeline shapes with **this demo's
endpoints**, shown side by side with the **equivalent real Databricks code**
(PySpark / DLT / Workflows). The demo runs locally; the right-hand column is what
you'd write in a Databricks workspace (see `CLOUD_PROMOTION.md` for getting
there).

> All examples assume a cluster and catalog exist:
> ```bash
> curl -X POST localhost:8000/clusters  -d '{"name":"analytics-cluster","size":"SMALL"}'  -H 'content-type: application/json'
> curl -X POST localhost:8000/catalog/catalogs -d '{"name":"main"}' -H 'content-type: application/json'
> ```

---

## 1. Batch pipeline — Medallion via Workflows

Ingest raw → clean/dedupe → aggregate, orchestrated as a multi-task job.

### This demo

```bash
# Bronze: land raw events (append-only)
curl -X POST localhost:8000/medallion/bronze -H 'content-type: application/json' -d '{
  "table": "main.medallion.bronze_events",
  "rows": [{"event_id":1,"event_type":"click"},{"event_id":1,"event_type":"click"},
           {"event_id":2,"event_type":"view"},{"event_id":3,"event_type":null}]
}'

# Silver: dedupe on event_id, drop null event_type
curl -X POST localhost:8000/medallion/silver -H 'content-type: application/json' -d '{
  "source":"main.medallion.bronze_events","target":"main.medallion.silver_events",
  "dedupe_key":"event_id","drop_nulls_in":["event_type"]
}'

# Gold: counts by event_type
curl -X POST localhost:8000/medallion/gold -H 'content-type: application/json' -d '{
  "source":"main.medallion.silver_events","target":"main.medallion.gold_event_counts",
  "group_by":["event_type"]
}'

# Orchestrate the same hops as a Workflow (DAG)
curl -X POST localhost:8000/jobs -H 'content-type: application/json' -d '{
  "name":"medallion_job","cluster":"analytics-cluster",
  "tasks":[
    {"key":"bronze","sql":"SELECT 1","depends_on":[]},
    {"key":"silver","sql":"SELECT 1","depends_on":["bronze"]},
    {"key":"gold","sql":"SELECT 1","depends_on":["silver"]}
  ]
}'
curl -X POST localhost:8000/jobs/medallion_job/run
```

### Real Databricks (PySpark notebook tasks)

```python
# Bronze
raw = spark.read.json("s3://landing/events/")
raw.write.format("delta").mode("append").saveAsTable("main.medallion.bronze_events")

# Silver
from pyspark.sql import functions as F
bronze = spark.table("main.medallion.bronze_events")
silver = (bronze.where(F.col("event_type").isNotNull())
                .dropDuplicates(["event_id"]))
silver.write.format("delta").mode("overwrite").saveAsTable("main.medallion.silver_events")

# Gold
gold = spark.table("main.medallion.silver_events").groupBy("event_type").count()
gold.write.format("delta").mode("overwrite").saveAsTable("main.medallion.gold_event_counts")
```

Databricks **Jobs YAML** (Asset Bundle) for the DAG:

```yaml
resources:
  jobs:
    medallion_job:
      name: medallion_job
      tasks:
        - task_key: bronze
          notebook_task: { notebook_path: ../src/bronze }
        - task_key: silver
          depends_on: [{ task_key: bronze }]
          notebook_task: { notebook_path: ../src/silver }
        - task_key: gold
          depends_on: [{ task_key: silver }]
          notebook_task: { notebook_path: ../src/gold }
```

---

## 2. Streaming pipeline — Auto Loader → Bronze

Incrementally ingest files as they land, exactly once.

### This demo

```bash
curl -X POST localhost:8000/autoloader -H 'content-type: application/json' -d '{
  "name":"events_loader","source_dir":"incoming","format":"json",
  "target":"main.bronze.raw_events"
}'

# Land files (in real life they arrive in cloud storage)
curl -X PUT localhost:8000/autoloader/events_loader/files -F 'file=@sample_data/events.json'

# Trigger-once micro-batch: processes only NEW files, advances the checkpoint
curl -X POST localhost:8000/autoloader/events_loader/trigger -d '{"trigger_once":true}' -H 'content-type: application/json'

# Inspect the checkpoint / offset
curl localhost:8000/autoloader/events_loader
```

### Real Databricks (Auto Loader)

```python
(spark.readStream
   .format("cloudFiles")
   .option("cloudFiles.format", "json")
   .option("cloudFiles.schemaLocation", "s3://chk/events/schema")
   .load("s3://landing/events/")
 .writeStream
   .option("checkpointLocation", "s3://chk/events/")
   .trigger(availableNow=True)              # process all available, then stop
   .toTable("main.bronze.raw_events"))
```

The demo's "processed-files set" in MongoDB is the analogue of Auto Loader's
`checkpointLocation` + `cloudFiles` file-notification/listing state.

---

## 3. Data-quality pipeline — Delta Live Tables + expectations

Declare tables and the rules rows must satisfy; quarantine or fail on violations.

### This demo

```bash
curl -X POST localhost:8000/dlt -H 'content-type: application/json' -d '{
  "name":"orders_pipeline","target_catalog":"main","target_schema":"dlt",
  "steps":[
    {"name":"raw_orders",
     "query":"SELECT * FROM (VALUES (1,100.0),(2,-5.0),(3,50.0)) AS t(order_id, amount)",
     "depends_on":[]},
    {"name":"clean_orders","query":"SELECT * FROM raw_orders","depends_on":["raw_orders"],
     "expectations":[{"name":"positive_amount","constraint":"amount > 0","action":"DROP"}]}
  ]
}'
curl -X POST localhost:8000/dlt/orders_pipeline/run -d '{}' -H 'content-type: application/json'
# -> report shows clean_orders: rows_in=3, rows_written=2, positive_amount.quarantined=1
```

### Real Databricks (DLT)

```python
import dlt
from pyspark.sql import functions as F

@dlt.table
def raw_orders():
    return spark.read.format("delta").load("s3://landing/orders/")

@dlt.table
@dlt.expect_or_drop("positive_amount", "amount > 0")   # DROP violating rows
def clean_orders():
    return dlt.read("raw_orders")
```

Action mapping: `@dlt.expect` → `WARN`, `@dlt.expect_or_drop` → `DROP`,
`@dlt.expect_or_fail` → `FAIL` (all three supported by `DLTExpectation.action`).

---

## 4. Orchestration — Workflows DAG with fan-out / fan-in

Multiple tasks with dependencies; downstream tasks skip if an upstream fails.

### This demo

```bash
curl -X POST localhost:8000/jobs -H 'content-type: application/json' -d '{
  "name":"etl","cluster":"analytics-cluster","schedule_seconds":3600,
  "tasks":[
    {"key":"ingest","sql":"SELECT 1","depends_on":[]},
    {"key":"transform_a","sql":"SELECT 2","depends_on":["ingest"]},
    {"key":"transform_b","sql":"SELECT 3","depends_on":["ingest"]},
    {"key":"publish","sql":"SELECT 4","depends_on":["transform_a","transform_b"]}
  ]
}'
curl -X POST localhost:8000/jobs/etl/run
curl localhost:8000/jobs/etl/runs     # per-task SUCCEEDED/FAILED/SKIPPED + run order
```

`schedule_seconds` registers the job with APScheduler (the cron analogue). The
run executes `ingest → {transform_a, transform_b} → publish`; if `ingest` fails,
the rest are `SKIPPED`.

### Real Databricks (Jobs YAML)

```yaml
resources:
  jobs:
    etl:
      name: etl
      schedule: { quartz_cron_expression: "0 0 * * * ?", timezone_id: "UTC" }
      tasks:
        - { task_key: ingest,      notebook_task: { notebook_path: ../src/ingest } }
        - { task_key: transform_a, depends_on: [{task_key: ingest}], notebook_task: {notebook_path: ../src/ta} }
        - { task_key: transform_b, depends_on: [{task_key: ingest}], notebook_task: {notebook_path: ../src/tb} }
        - { task_key: publish,     depends_on: [{task_key: transform_a},{task_key: transform_b}], notebook_task: {notebook_path: ../src/publish} }
```

---

## Putting it together

A production Lakehouse typically chains these: **Auto Loader** ingests files into
**Bronze**, **DLT** (or notebooks) refine Bronze→Silver→Gold with **expectations**,
**Workflows** schedule and orchestrate the whole thing, **Unity Catalog** governs
access and tracks **lineage**, **Databricks SQL** serves Gold to BI, and
**MLflow** trains/registers models on the same Gold features. Every endpoint in
this demo maps onto one of those stages — run `python demo.py` to see the whole
chain execute end-to-end.
