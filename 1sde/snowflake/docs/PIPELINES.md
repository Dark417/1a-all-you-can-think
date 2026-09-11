# Building Data Pipelines on Snowflake

This guide shows the canonical Snowflake pipeline patterns. For each, you get:
1. The **real Snowflake SQL** you would write.
2. The **equivalent call** against this local demo so you can run it now.

The reference pattern is the **continuous ELT pipeline**:

```
   files          ┌────────┐  COPY/Snowpipe   ┌─────────┐
  (S3/GCS) ──────▶│ STAGE  │─────────────────▶│  RAW    │  (landing / bronze)
                  └────────┘                  └─────────┘
                                                   │ STREAM (CDC)
                                                   ▼
                                              ┌─────────┐
                                     TASK ───▶│ STAGING │  (cleaned / silver)
                                              └─────────┘
                                                   │ STREAM
                                                   ▼
                                              ┌─────────┐
                                     TASK ───▶│  MARTS  │  (aggregated / gold)
                                              └─────────┘
```

This is the Snowflake spelling of the **medallion (bronze→silver→gold)**
architecture, orchestrated declaratively with **Streams + Tasks**.

---

## Step 0 — Provision compute and namespace

**Snowflake**
```sql
CREATE WAREHOUSE ETL_WH WITH WAREHOUSE_SIZE = 'XSMALL' AUTO_SUSPEND = 60;
CREATE DATABASE ANALYTICS;
CREATE SCHEMA  ANALYTICS.RAW;
CREATE SCHEMA  ANALYTICS.MARTS;
```

**This demo**
```bash
curl -X POST localhost:8000/warehouses -H 'content-type: application/json' \
  -d '{"name":"ETL_WH","size":"X-SMALL","auto_suspend_seconds":60}'
curl -X POST localhost:8000/databases -d '{"name":"ANALYTICS"}' -H 'content-type: application/json'
curl -X POST localhost:8000/databases/schemas -H 'content-type: application/json' \
  -d '{"database":"ANALYTICS","name":"RAW"}'
curl -X POST localhost:8000/databases/schemas -H 'content-type: application/json' \
  -d '{"database":"ANALYTICS","name":"MARTS"}'
```

---

## Step 1 — Land raw files in a stage

**Snowflake**
```sql
CREATE STAGE ANALYTICS.RAW.LANDING;
CREATE FILE FORMAT ANALYTICS.RAW.CSV_FF TYPE = CSV SKIP_HEADER = 1;

-- from SnowSQL / a driver:
PUT file://./customers.csv @ANALYTICS.RAW.LANDING;
```

**This demo**
```bash
curl -X POST localhost:8000/stages -d '{"name":"LANDING"}' -H 'content-type: application/json'
curl -X POST localhost:8000/stages/file-formats -H 'content-type: application/json' \
  -d '{"name":"CSV_FF","type":"CSV","options":{"header":true}}'
curl -X PUT  localhost:8000/stages/LANDING/files -F 'file=@sample_data/customers.csv'
```

---

## Step 2 — Bulk load (COPY INTO) and/or continuous load (Snowpipe)

**Bulk — Snowflake**
```sql
CREATE TABLE ANALYTICS.RAW.CUSTOMERS (id INT, name STRING, profile VARIANT);
COPY INTO ANALYTICS.RAW.CUSTOMERS
  FROM @ANALYTICS.RAW.LANDING
  FILE_FORMAT = (FORMAT_NAME = ANALYTICS.RAW.CSV_FF)
  PATTERN = '.*[.]csv';
```

**Bulk — this demo**
```bash
curl -X POST localhost:8000/tables -H 'content-type: application/json' -d '{
  "database":"ANALYTICS","schema":"RAW","name":"CUSTOMERS",
  "columns":[{"name":"id","type":"INTEGER"},{"name":"name","type":"VARCHAR"},
             {"name":"profile","type":"VARIANT"}]}'
curl -X POST localhost:8000/stages/copy-into -H 'content-type: application/json' -d '{
  "table":"ANALYTICS.RAW.CUSTOMERS","stage":"LANDING","pattern":"*.csv",
  "file_format":"CSV_FF","warehouse":"ETL_WH"}'
```

**Continuous — Snowflake (Snowpipe)**
```sql
CREATE PIPE ANALYTICS.RAW.CUST_PIPE AUTO_INGEST = TRUE AS
  COPY INTO ANALYTICS.RAW.CUSTOMERS FROM @ANALYTICS.RAW.LANDING
  FILE_FORMAT = (FORMAT_NAME = ANALYTICS.RAW.CSV_FF);
-- new files in the bucket trigger auto-ingest via cloud notifications.
```

**Continuous — this demo**
```bash
curl -X POST localhost:8000/stages/pipes -H 'content-type: application/json' -d '{
  "name":"CUST_PIPE","auto_ingest":true,
  "copy_statement":{"table":"ANALYTICS.RAW.CUSTOMERS","stage":"LANDING",
                    "pattern":"auto_*.csv","file_format":"CSV_FF"}}'
# now upload a matching file -> it is ingested automatically:
curl -X PUT localhost:8000/stages/LANDING/files -F 'file=@auto_batch1.csv'
curl localhost:8000/stages/pipes        # files_loaded > 0
```

---

## Step 3 — Capture changes with a Stream

**Snowflake**
```sql
CREATE STREAM ANALYTICS.RAW.CUSTOMERS_STREAM ON TABLE ANALYTICS.RAW.CUSTOMERS;
-- later, inspect pending changes:
SELECT * FROM ANALYTICS.RAW.CUSTOMERS_STREAM;   -- rows + METADATA$ACTION
```

**This demo**
```bash
curl -X POST localhost:8000/streams -H 'content-type: application/json' \
  -d '{"name":"CUSTOMERS_STREAM","on_table":"ANALYTICS.RAW.CUSTOMERS"}'
curl localhost:8000/streams/CUSTOMERS_STREAM           # pending CDC changes
```

---

## Step 4 — Transform incrementally with a Task (Stream + Task pattern)

The idiomatic Snowflake pipeline: a scheduled **task** consumes a **stream** and
MERGEs only the changed rows downstream — incremental, not full-refresh.

**Snowflake**
```sql
CREATE TABLE ANALYTICS.MARTS.CUSTOMER_TIERS (tier STRING, n NUMBER);

CREATE TASK ANALYTICS.MARTS.REFRESH_TIERS
  WAREHOUSE = ETL_WH
  SCHEDULE  = '1 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('ANALYTICS.RAW.CUSTOMERS_STREAM')
AS
  MERGE INTO ANALYTICS.MARTS.CUSTOMER_TIERS t
  USING (
    SELECT profile:tier::string AS tier, COUNT(*) n
    FROM ANALYTICS.RAW.CUSTOMERS_STREAM GROUP BY 1
  ) s ON t.tier = s.tier
  WHEN MATCHED THEN UPDATE SET n = t.n + s.n
  WHEN NOT MATCHED THEN INSERT (tier, n) VALUES (s.tier, s.n);

ALTER TASK ANALYTICS.MARTS.REFRESH_TIERS RESUME;   -- tasks start suspended
```

**This demo** (DuckDB SQL; physical schema name is `DATABASE$SCHEMA`)
```bash
curl -X POST localhost:8000/tables -H 'content-type: application/json' -d '{
  "database":"ANALYTICS","schema":"MARTS","name":"CUSTOMER_TIERS",
  "columns":[{"name":"tier","type":"VARCHAR"},{"name":"n","type":"INTEGER"}]}'

curl -X POST localhost:8000/tasks -H 'content-type: application/json' -d '{
  "name":"REFRESH_TIERS","warehouse":"ETL_WH","schedule_seconds":60,
  "sql":"INSERT INTO \"ANALYTICS$MARTS\".\"CUSTOMER_TIERS\" SELECT profile->>'\''tier'\'' AS tier, COUNT(*) FROM \"ANALYTICS$RAW\".\"CUSTOMERS\" GROUP BY 1"}'

curl -X POST localhost:8000/tasks/REFRESH_TIERS/resume   # begin scheduling
curl -X POST localhost:8000/tasks/REFRESH_TIERS/run      # or run once, now
curl localhost:8000/tasks/REFRESH_TIERS/history
```

### Building a DAG
Add child tasks that run `AFTER` a parent to form a dependency graph:
```bash
curl -X POST localhost:8000/tasks -H 'content-type: application/json' -d '{
  "name":"NOTIFY_DONE","warehouse":"ETL_WH","after":"REFRESH_TIERS",
  "sql":"SELECT 1"}'
# running the root runs the whole subtree:
curl -X POST localhost:8000/tasks/REFRESH_TIERS/run
```

---

## Step 5 — Verify, observe, and control cost

```bash
curl localhost:8000/tables/ANALYTICS.MARTS.CUSTOMER_TIERS/data      # results
curl localhost:8000/time-travel/ANALYTICS.RAW.CUSTOMERS/history     # versions
curl localhost:8000/governance/query-history?limit=20              # audit
curl localhost:8000/warehouses/ETL_WH/usage                        # credits

# guardrail: suspend the warehouse automatically if it burns > quota credits
curl -X POST localhost:8000/governance/resource-monitors -H 'content-type: application/json' \
  -d '{"name":"ETL_MON","credit_quota":5,"on_breach":"SUSPEND","warehouses":["ETL_WH"]}'
curl localhost:8000/governance/resource-monitors/evaluate
```

---

## Pattern cheat-sheet

| Goal | Snowflake objects | Demo endpoints |
|---|---|---|
| One-off / scheduled bulk load | `COPY INTO` | `POST /stages/copy-into` |
| Continuous file ingestion | Snowpipe (`PIPE`) | `POST /stages/pipes` |
| Incremental transform | `STREAM` + `TASK` + `MERGE` | `/streams`, `/tasks` |
| Multi-step orchestration | Task DAG (`AFTER`) | `/tasks` with `after` |
| Dev/test copy of prod | Zero-copy `CLONE` | `POST /time-travel/clone` |
| Recover from bad write | Time Travel / `UNDROP` | `POST /time-travel/{t}/restore` |
| Cost control | Resource Monitor | `/governance/resource-monitors` |
| Cross-team data access | Secure Share | `POST /governance/shares` |

### Best practices carried over from real Snowflake
- **Separate warehouses per workload** (ETL vs BI vs DS) for isolation.
- **Right-size, don't over-size**: scale *up* for big single queries, use
  *multi-cluster* for concurrency.
- **Load in bulk, transform incrementally** (Stream+Task), never full-refresh
  large tables.
- **Stage as VARIANT first**, then flatten — keeps raw fidelity and replays.
- **Use Tasks' `WHEN SYSTEM$STREAM_HAS_DATA`** to avoid burning credits on
  empty runs.
- Treat all DDL as code (see `CLOUD_PROMOTION.md` for CI/CD).

➡️ Next: **[CLOUD_PROMOTION.md](CLOUD_PROMOTION.md)** — moving this to real
Snowflake on AWS or GCP.
