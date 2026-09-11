# Promoting the Demo to Real Snowflake (AWS / GCP)

This local project emulates Snowflake's *behavior*. This document explains what
it takes to run the **same pipelines on real Snowflake**, deployed on **AWS** or
**GCP**, and what changes versus the local demo.

> TL;DR: Snowflake itself is a fully managed SaaS — you never provision the
> warehouse software, VMs, or storage cluster. "Deploying to AWS/GCP" mostly
> means **choosing the cloud + region for your Snowflake account** and **wiring
> up your own cloud buckets, networking, identity, and CI/CD** around it.

---

## 1. Concept mapping: demo → real Snowflake

| Local demo | Real Snowflake |
|---|---|
| DuckDB file (storage) | Micro-partitions on **S3** (AWS) / **GCS** (GCP), managed by Snowflake |
| MongoDB catalog | Snowflake's internal metadata (Cloud Services) — nothing to run |
| FastAPI endpoints | SQL via SnowSQL / drivers / Snowsight / REST SQL API |
| `engine.py` credit metering | Real per-second **credit** billing |
| Local `stages/` dir | Internal stages, or **external stages** on S3/GCS |
| `_maybe_trigger_pipes` | **Snowpipe** auto-ingest via S3 Event Notifications / GCS Pub/Sub |
| mongomock fallback | n/a (Snowflake is always managed) |
| RBAC documents | Real RBAC enforced by Cloud Services |

The key inversion: locally *you* run the engine; in production Snowflake runs it
and you bring **data, identity, network, and code**.

---

## 2. Get a Snowflake account on your chosen cloud

When you create a Snowflake account (or an org + accounts), you pick:
- **Cloud provider**: AWS, GCP, or Azure.
- **Region**: e.g. `us-east-1` (AWS), `us-central1` (GCP).
- **Edition**: Standard / Enterprise (Time Travel up to 90d, multi-cluster) /
  Business Critical (HIPAA/PCI, Tri-Secret) / VPS.

Each account is pinned to one cloud+region; cross-region/cross-cloud needs
**Replication**. Provision accounts via the **Organization** UI, the
[Terraform Snowflake provider](https://registry.terraform.io/providers/Snowflake-Labs/snowflake/latest),
or (for the account itself) the cloud Marketplace listing.

---

## 3. What *you* must provide on AWS

Snowflake runs in Snowflake's own cloud account, but it reaches into yours for
data and identity.

1. **External stage storage — S3**
   - Create an S3 bucket for raw files.
   - Create an **IAM role** that Snowflake's account can assume (trust policy
     references the Snowflake-provided IAM user ARN + external ID).
   - Register it as a **Storage Integration**:
     ```sql
     CREATE STORAGE INTEGRATION s3_int
       TYPE = EXTERNAL_STAGE STORAGE_PROVIDER = 'S3' ENABLED = TRUE
       STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::123456789012:role/snowflake-s3'
       STORAGE_ALLOWED_LOCATIONS = ('s3://my-bucket/raw/');
     CREATE STAGE raw_ext STORAGE_INTEGRATION = s3_int URL = 's3://my-bucket/raw/';
     ```
2. **Snowpipe auto-ingest**
   - Configure **S3 Event Notifications → SQS** (Snowflake provides the SQS ARN
     from `DESCRIBE PIPE`). New objects then trigger ingestion automatically.
3. **Networking / security (optional but common)**
   - **AWS PrivateLink** for private connectivity to Snowflake.
   - **Network policies** to allow-list IP/CIDR ranges.
   - **Tri-Secret Secure**: bring your own key via **AWS KMS**.
4. **Identity federation**
   - SSO via SAML/OAuth (Okta, Entra ID, etc.); SCIM for user/role provisioning.

---

## 4. What *you* must provide on GCP

Same shape, GCP services:

1. **External stage storage — GCS**
   - Create a GCS bucket.
   - `CREATE STORAGE INTEGRATION` with `STORAGE_PROVIDER = 'GCS'`; Snowflake
     generates a **service account** — grant it
     `roles/storage.objectViewer` (+ `objectAdmin` to write) on the bucket.
     ```sql
     CREATE STORAGE INTEGRATION gcs_int
       TYPE = EXTERNAL_STAGE STORAGE_PROVIDER = 'GCS' ENABLED = TRUE
       STORAGE_ALLOWED_LOCATIONS = ('gcs://my-bucket/raw/');
     DESC STORAGE INTEGRATION gcs_int;  -- shows the SA email to grant
     ```
2. **Snowpipe auto-ingest**
   - **GCS → Pub/Sub** notifications; subscribe Snowflake's provided
     notification channel.
3. **Networking / security**
   - **Google Private Service Connect** for private connectivity.
   - Network policies; **Cloud KMS** for customer-managed keys.
4. **Identity**: SSO/SCIM as above.

---

## 5. Promote the demo's objects (1:1 SQL)

Everything you exercised via REST maps to plain SQL DDL/DML you can version and
deploy. The pipeline from `PIPELINES.md` becomes:

```sql
USE ROLE SYSADMIN;
CREATE WAREHOUSE ETL_WH WAREHOUSE_SIZE='XSMALL' AUTO_SUSPEND=60 AUTO_RESUME=TRUE;
CREATE DATABASE ANALYTICS;  CREATE SCHEMA ANALYTICS.RAW;  CREATE SCHEMA ANALYTICS.MARTS;

CREATE STAGE  ANALYTICS.RAW.LANDING STORAGE_INTEGRATION = s3_int URL='s3://my-bucket/raw/';
CREATE FILE FORMAT ANALYTICS.RAW.CSV_FF TYPE=CSV SKIP_HEADER=1;
CREATE TABLE  ANALYTICS.RAW.CUSTOMERS (id INT, name STRING, profile VARIANT);

CREATE PIPE   ANALYTICS.RAW.CUST_PIPE AUTO_INGEST=TRUE AS
  COPY INTO ANALYTICS.RAW.CUSTOMERS FROM @ANALYTICS.RAW.LANDING
  FILE_FORMAT=(FORMAT_NAME=ANALYTICS.RAW.CSV_FF);

CREATE STREAM ANALYTICS.RAW.CUSTOMERS_STREAM ON TABLE ANALYTICS.RAW.CUSTOMERS;
CREATE TASK   ANALYTICS.MARTS.REFRESH_TIERS WAREHOUSE=ETL_WH SCHEDULE='1 MINUTE'
  WHEN SYSTEM$STREAM_HAS_DATA('ANALYTICS.RAW.CUSTOMERS_STREAM') AS <merge...>;
ALTER TASK ANALYTICS.MARTS.REFRESH_TIERS RESUME;
```

> Note the differences from the demo: physical names are plain
> `DB.SCHEMA.TABLE` (no `DATABASE$SCHEMA` encoding), VARIANT paths use
> `profile:tier::string`, and stages point at real S3/GCS URLs via a storage
> integration.

---

## 6. CI/CD and Infrastructure-as-Code

Treat all of the above as code:

- **Schema/object change management**: [schemachange](https://github.com/Snowflake-Labs/schemachange)
  (migration-style SQL), **dbt** (models/tests/docs for the transform layer), or
  Flyway/Liquibase.
- **Infrastructure**: **Terraform Snowflake provider** for warehouses,
  databases, roles, grants, integrations — plus the AWS/GCP providers for the
  bucket, IAM role/service account, and notifications. One `terraform apply`
  stands up the cloud side *and* the Snowflake side.
- **Pipeline**: GitHub Actions / GitLab CI runs `terraform apply` then
  `dbt build` / `schemachange deploy` on merge to `main`, against separate
  **dev / staging / prod** accounts or databases.
- **Secrets**: store the Snowflake key-pair / OAuth creds in the CI secret store
  (GitHub OIDC → short-lived creds is ideal); never in the repo.
- **Environments via Zero-Copy Clone**: `CREATE DATABASE ANALYTICS_DEV CLONE
  ANALYTICS;` gives an instant, isolated prod-like dev DB.

---

## 7. Migrating the data itself

1. Land your existing files in the S3/GCS bucket behind the external stage.
2. `COPY INTO` historical data once (bulk), then let Snowpipe handle ongoing
   arrivals.
3. For DB-to-Snowflake migration, use a CDC tool (Fivetran, Debezium→Kafka→
   Snowpipe Streaming, AWS DMS) feeding the RAW layer; the Stream+Task layer is
   unchanged.

---

## 8. Checklist to go live

- [ ] Snowflake account created on AWS or GCP, region chosen, edition fits your
      Time-Travel/compliance needs.
- [ ] S3/GCS bucket + Storage Integration + external stage working
      (`LIST @stage` succeeds).
- [ ] Snowpipe wired to S3 SQS / GCS Pub/Sub; test file auto-ingests.
- [ ] Warehouses sized per workload with `AUTO_SUSPEND`; **Resource Monitors**
      set for spend guardrails.
- [ ] RBAC: `SYSADMIN`-owned objects, least-privilege custom roles, `PUBLIC`
      locked down; SSO/SCIM connected.
- [ ] Network policy / PrivateLink / Private Service Connect as required.
- [ ] All DDL in Git; Terraform + dbt/schemachange deploying via CI to
      dev→staging→prod.
- [ ] Observability: `SNOWFLAKE.ACCOUNT_USAGE` dashboards for cost & query
      performance; alerts on Resource Monitor breaches.

---

## 9. AWS vs GCP at a glance

| Need | AWS | GCP |
|---|---|---|
| External stage storage | S3 | GCS |
| Cloud identity for stage | IAM role + external ID | Snowflake-generated service account |
| Snowpipe notifications | S3 Events → SQS | GCS → Pub/Sub |
| Private connectivity | AWS PrivateLink | Private Service Connect |
| Customer-managed keys | AWS KMS | Cloud KMS |
| Secrets in CI | Secrets Manager / OIDC | Secret Manager / Workload Identity |

The Snowflake SQL layer is **identical across clouds** — only the storage URL,
the identity object, and the notification plumbing differ. That portability is a
core Snowflake selling point.
