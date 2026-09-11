# Databricks Lakehouse — Local Functionality Demo

A **fully local, runnable** demonstration of the Databricks **Lakehouse
Platform**, exposed as a REST API with an interactive Swagger UI.

The headline: the storage layer is **real**. Tables are genuine **Delta Lake**
tables written by [**delta-rs**](https://github.com/delta-io/delta-rs) (a
pure-Rust implementation — **no Spark, no JVM**). The `_delta_log` transaction
log and Parquet data files this produces are byte-for-byte the same open format
a Databricks cluster reads. ACID commits, `MERGE` upserts, time travel, schema
evolution, `OPTIMIZE`/Z-ORDER and `VACUUM` all genuinely work.

Everything else is emulated with lightweight local tech so it runs with zero
infrastructure:

| Databricks layer | Emulated locally by | Real or emulated? |
|---|---|---|
| **Lakehouse storage** — Delta Lake on S3/GCS/ADLS | **delta-rs** → real Delta tables on disk | **Real** Delta format |
| **Compute** — clusters / SQL warehouses, Photon, DBUs | **DuckDB** with per-cluster thread budgets + DBU metering | Emulated billing, real query engine |
| **Unity Catalog** — 3-level namespace, grants, lineage | **MongoDB** (catalogs / schemas / tables / grants / lineage edges) | Emulated metastore |
| **MLflow** — tracking + model registry | **real MLflow** (local sqlite backend) | **Real** MLflow |
| **Control-plane services** | **FastAPI** + MongoDB | Emulated |

This is the Databricks sibling of the `snowflake/` project in this repo and
mirrors its architecture (FastAPI routers + Swagger, MongoDB catalog with
mongomock fallback, hermetic `demo.py`, pytest suite, docker-compose, Makefile).

## Snowflake ↔ Databricks analogy

| Concept | Snowflake | Databricks (this demo) |
|---|---|---|
| Storage | Micro-partitions (proprietary) | **Delta Lake** (open: log + Parquet) |
| Compute | Virtual warehouses, credits | **Clusters / SQL warehouses**, DBUs |
| Namespace | `database.schema.table` | `catalog.schema.table` (**Unity Catalog**) |
| Governance | RBAC roles & grants | Unity Catalog grants + **lineage** |
| Bulk/continuous ingest | Stages, `COPY INTO`, Snowpipe | **Auto Loader** / Structured Streaming |
| Change tracking | Streams (CDC) | Delta `MERGE` + transaction log |
| Scheduled pipelines | Tasks (DAG) | **Workflows / Jobs** (multi-task DAG) |
| Declarative ETL + DQ | — | **Delta Live Tables** + expectations |
| Time travel | `AT (VERSION => n)` | Delta `VERSION AS OF n` |
| ML lifecycle | Snowpark ML / partners | **MLflow** + Model Registry |

## Quickstart

### Option A — zero infrastructure (recommended first run)

```bash
pip install -r requirements.txt
python demo.py            # hermetic end-to-end walkthrough of every feature
python -m pytest tests/   # the test suite
```

`demo.py` forces the in-memory MongoDB (mongomock) and uses throwaway temp dirs
for the Delta tables, MLflow store and Auto Loader stage, so it needs nothing
running. It exercises **all 12 routers** and prints an `OK`/`ERR` line per step.

### Option B — interactive API + Swagger UI

```bash
uvicorn app.main:app --reload
# open http://localhost:8000/docs
```

### Option C — full Docker stack (real MongoDB + Mongo Express)

```bash
docker compose up --build
# Swagger UI:    http://localhost:8000/docs
# Mongo Express: http://localhost:8081   (browse the Unity Catalog metastore)
```

A `Makefile` wraps these: `make install | demo | test | serve | up | down | clean`.

## Swagger UI tour

The routers are ordered `0..11` in the Swagger UI. A natural path:

1. **`POST /clusters`** — create a Photon, autoscaling, DBU-metered cluster.
2. **`POST /catalog/catalogs`**, **`/catalog/schemas`** — the `catalog.schema.table` namespace.
3. **`POST /delta`** then `append` / **`merge`** / `update` / `delete` — the Delta core.
   - `GET /delta/{fqn}/history` and `GET /delta/{fqn}/data?version=1` — **time travel**.
   - `POST /delta/{fqn}/optimize`, `/zorder`, `/vacuum` — table maintenance.
4. **`POST /sql`** — query the Delta table on the cluster (DuckDB `delta_scan`), with result cache.
5. **`POST /medallion/bronze|silver|gold`** — the flagship multi-hop pipeline (records lineage).
6. **`POST /autoloader`** + `trigger` — incremental, exactly-once file ingestion.
7. **`POST /dlt`** + `run` — declarative pipeline DAG with **data-quality expectations**.
8. **`POST /jobs`** + `run` — multi-task **Workflows** DAG with per-task status.
9. **`POST /notebooks`** + `run` — execute SQL/Python cells on a cluster.
10. **`POST /mlflow/experiments`**, `/runs`, `/models` — tracking + **Model Registry** (Staging/Production).
11. **`GET /governance/lineage`** — the Unity Catalog **data lineage graph**.

## Feature checklist → endpoint

| Databricks feature | Endpoint(s) |
|---|---|
| Cluster create/start/terminate/resize | `POST /clusters`, `/clusters/{n}/start|terminate|resize` |
| Autoscaling config + DBU metering | `ClusterCreate.{min,max}_workers`, `GET /clusters/{n}/usage` |
| Unity Catalog 3-level namespace | `POST /catalog/catalogs`, `/catalog/schemas`; `catalog.schema.table` everywhere |
| Grants + effective privileges | `POST /catalog/grants`, `/revoke`; `GET /catalog/effective-privileges` |
| Create Delta table | `POST /delta` |
| Append / **MERGE (upsert)** / UPDATE / DELETE | `POST /delta/{fqn}/append|merge|update|delete` |
| **Time travel** (version) + history | `GET /delta/{fqn}/data?version=N`, `/delta/{fqn}/history` |
| **Schema evolution** | `POST /delta/{fqn}/append` with `evolve_schema=true` |
| **OPTIMIZE** / **Z-ORDER** / **VACUUM** | `POST /delta/{fqn}/optimize|zorder|vacuum` |
| DESCRIBE DETAIL | `GET /delta/{fqn}/describe-detail` |
| Databricks SQL on a cluster + result cache | `POST /sql` |
| Medallion Bronze→Silver→Gold + lineage | `POST /medallion/bronze|silver|gold` |
| **Auto Loader** incremental ingest + checkpoint | `POST /autoloader`, `/autoloader/{n}/trigger`, `GET /autoloader/{n}` |
| **Delta Live Tables** + expectations (WARN/DROP/FAIL) | `POST /dlt`, `/dlt/{n}/run` |
| **Workflows / Jobs** multi-task DAG + schedule | `POST /jobs`, `/jobs/{n}/run`, `GET /jobs/{n}/runs` |
| Notebooks (SQL + Python cells) | `POST /notebooks`, `/notebooks/{n}/run` |
| **MLflow** experiments / runs / registry / stages | `POST /mlflow/experiments|runs`, `GET /mlflow/runs|models`, `POST /mlflow/models/transition` |
| **Lineage** graph + upstream + audit + grants summary | `GET /governance/lineage`, `/lineage/{fqn}/upstream`, `/query-history`, `/grants-summary` |

## Project layout

```
databricks/
├── app/
│   ├── core/
│   │   ├── config.py       # env-driven settings (delta/stage/mlruns dirs)
│   │   ├── catalog.py      # MongoDB metastore + mongomock fallback
│   │   ├── delta_io.py     # delta-rs wrappers (the storage layer)
│   │   ├── engine.py       # DuckDB SQL warehouse + DBU metering + result cache
│   │   ├── naming.py       # catalog.schema.table parsing + on-disk paths
│   │   ├── metastore.py    # register tables / auto-create namespaces
│   │   └── lineage.py      # Unity Catalog lineage edges
│   ├── routers/            # one module per numbered feature area (0..11)
│   ├── models.py           # Pydantic request/response models (power Swagger)
│   └── main.py             # FastAPI app, ordered openapi_tags, /docs
├── demo.py                 # hermetic end-to-end walkthrough (53 steps)
├── tests/test_api.py       # pytest suite (15 tests)
├── sample_data/            # CSV/JSON samples
├── docs/                   # ARCHITECTURE, PIPELINES, CLOUD_PROMOTION
├── Dockerfile, docker-compose.yml, Makefile, requirements.txt, .env.example
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the deep dive,
[`docs/PIPELINES.md`](docs/PIPELINES.md) for building batch/streaming/DQ
pipelines (with side-by-side real Databricks code), and
[`docs/CLOUD_PROMOTION.md`](docs/CLOUD_PROMOTION.md) for promoting this demo to
real Databricks on AWS and GCP.
