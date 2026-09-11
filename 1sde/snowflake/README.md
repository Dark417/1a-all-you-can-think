# Snowflake Functionality Demo — local, runnable, with Swagger UI

A **fully local, dependency-light** project that demonstrates Snowflake's core
functionality and architecture. Every feature is a REST endpoint you can drive
from an **interactive Swagger UI**, backed by:

- **DuckDB** as the query engine (the *compute + storage* layers).
- **MongoDB** as the metadata catalog (the *cloud services* layer) — with an
  automatic in-memory **mongomock** fallback so it runs with **zero infra**.
- **FastAPI** serving the API + Swagger UI.

> Want the theory first? Read **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** —
> a deep dive into Snowflake's three-layer, multi-cluster shared-data design and
> exactly how each piece is emulated here.

---

## Quickstart (no Docker, no MongoDB needed)

```bash
cd snowflake
pip install -r requirements.txt

# 1) Run the scripted end-to-end walkthrough (exercises EVERY feature):
python demo.py

# 2) Or start the API + Swagger UI:
uvicorn app.main:app --reload
#   → open http://localhost:8000/docs
```

`demo.py` forces the in-memory catalog and an in-memory engine, so it needs no
MongoDB and leaves nothing behind — a 40-step tour that prints each call and its
result.

### With Docker (real MongoDB + a catalog browser)

```bash
docker compose up --build
#   http://localhost:8000/docs   → Swagger UI
#   http://localhost:8081        → Mongo Express (browse the metadata catalog)
```

### Run the tests

```bash
python -m pytest          # 9 hermetic tests covering every subsystem
# or: make test
```

---

## What's demonstrated (and where)

| # | Snowflake feature | Endpoints | Architecture notes |
|---|---|---|---|
| 1 | **Virtual Warehouses** — elastic compute, suspend/resume/resize, **credit metering** | `POST /warehouses`, `/{n}/resize`, `/suspend`, `/resume`, `/usage` | Storage/compute separation; per-size thread budget + credits |
| 2 | **Databases & Schemas** — 3-level namespace | `POST /databases`, `/databases/schemas` | `DB.SCHEMA.OBJECT` |
| 3 | **Tables & VARIANT** — structured + semi-structured; **micro-partitions** | `POST /tables`, `/{t}/insert`, `/{t}/data`, `/{t}/micro-partitions` | Parquet row-group min/max = pruning metadata |
| 4 | **SQL execution** on a warehouse + **result cache** | `POST /sql` | 24h result reuse, query history |
| 5 | **Stages, COPY INTO, Snowpipe** — bulk + continuous load | `POST /stages`, `PUT /stages/{s}/files`, `/copy-into`, `/pipes` | CSV/JSON/Parquet; auto-ingest |
| 6 | **Streams (CDC)** | `POST /streams`, `GET /streams/{n}`, `/consume` | Change tracking via version diffs |
| 7 | **Tasks** — scheduled SQL & **DAGs** | `POST /tasks`, `/resume`, `/run`, `/history` | Stream+Task pipelines |
| 8 | **Time Travel & Zero-Copy Clone** | `GET /time-travel/{t}/history`, `/at`, `POST /restore`, `/clone` | Immutable-storage superpowers |
| 9 | **RBAC** — roles, users, grants, **inheritance** | `POST /rbac/*`, `GET /rbac/.../effective-privileges`, `/check` | Role hierarchy resolution |
| 10 | **UDFs & Stored Procedures** — SQL + **real Python** | `POST /functions`, `/{n}/call` | Snowpark-style extensibility |
| 11 | **Secure Sharing, Resource Monitors, Query History** | `POST /governance/shares`, `/resource-monitors`, `/evaluate`, `GET /query-history` | No-copy sharing; spend guardrails |
| 0 | **Admin** — health, reset, architecture summary | `GET /admin/health`, `/architecture`, `POST /reset` | Shows the live metadata backend |

---

## Architecture at a glance

```
        Swagger UI / REST  ──►  FastAPI routers        ┐
                                                       │  Cloud Services layer
        Metadata (warehouses, roles, grants,           │  (the "brains")
        streams, tasks, history) ──►  MongoDB / mongomock ┘

        Query execution + credit metering ──►  DuckDB   ◄── Query Processing
                                                            (virtual warehouses)

        Table data + Parquet row groups ──►  DuckDB file ◄── Storage
                                                            (micro-partitions)
```

Each layer is independent — the defining property of Snowflake. See
**[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** for the full treatment.

---

## Project layout

```
snowflake/
├── app/
│   ├── main.py                # FastAPI app + Swagger UI config
│   ├── models.py              # Pydantic request/response models
│   ├── core/
│   │   ├── config.py          # env-driven settings (local defaults)
│   │   ├── catalog.py         # MongoDB / mongomock metadata catalog
│   │   ├── engine.py          # DuckDB engine: warehouses, credits, result cache
│   │   ├── history.py         # time-travel snapshots (powers Time Travel + Streams)
│   │   └── naming.py          # DB.SCHEMA.TABLE  ↔  DuckDB physical names
│   └── routers/               # one module per feature area (see table above)
├── demo.py                    # end-to-end scripted walkthrough (no infra)
├── tests/test_api.py          # hermetic pytest suite
├── sample_data/               # example CSV/JSON
├── docker-compose.yml         # Mongo + API + Mongo Express
├── Dockerfile · Makefile · requirements.txt · .env.example
└── docs/
    ├── ARCHITECTURE.md        # deep dive into Snowflake internals
    ├── PIPELINES.md           # build ELT pipelines (Snowflake SQL ↔ this demo)
    └── CLOUD_PROMOTION.md     # take it to real Snowflake on AWS / GCP
```

---

## Configuration

All settings have local-friendly defaults (see `.env.example`):

| Var | Default | Purpose |
|---|---|---|
| `MONGO_URI` | `mongodb://localhost:27017` | Catalog; falls back to mongomock if unreachable |
| `USE_MONGOMOCK` | _(unset)_ | Force in-memory catalog |
| `DUCKDB_PATH` | `./data/warehouse.duckdb` | Storage layer file (`:memory:` allowed) |
| `STAGE_DIR` | `./stages` | Internal-stage file location |
| `API_HOST` / `API_PORT` | `0.0.0.0` / `8000` | Server bind |

---

## Next steps

1. **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — how Snowflake really works.
2. **[docs/PIPELINES.md](docs/PIPELINES.md)** — build an end-to-end ELT pipeline,
   Snowflake SQL shown side-by-side with the demo calls.
3. **[docs/CLOUD_PROMOTION.md](docs/CLOUD_PROMOTION.md)** — what's required to run
   the same thing on real Snowflake on **AWS** or **GCP**.

> A parallel **[../databricks](../databricks)** project does the same for the
> Databricks Lakehouse.
