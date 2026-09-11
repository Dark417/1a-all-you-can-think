# Promoting to Real Databricks on AWS and GCP

This local demo deliberately mirrors Databricks concepts so the mental model
transfers directly. This guide is the concrete, practical path from *this repo*
to a *production Databricks workspace* on **AWS** and **GCP** — what to
provision, what replaces each emulated piece, and how to ship code and data.

> Databricks also runs on **Azure** (first-party "Azure Databricks"). This guide
> focuses on AWS and GCP as requested; the Azure equivalents are ADLS Gen2,
> Azure VNet injection, managed identities, and Key Vault.

---

## 0. Mapping: local demo concept → real Databricks / AWS / GCP

| Local demo | Real Databricks | AWS | GCP |
|---|---|---|---|
| `delta-rs` tables in `DELTA_DIR` | Delta tables on object storage | **S3** bucket | **GCS** bucket |
| `DuckDB` query engine | Clusters / SQL warehouses (Photon) | EC2 (data plane) | GCE/GKE (data plane) |
| MongoDB metastore | **Unity Catalog** metastore | UC metastore + S3 | UC metastore + GCS |
| `core/lineage.py` edges | Unity Catalog **lineage** (automatic) | — | — |
| `routers/clusters.py` | Cluster/SQL-warehouse APIs | EC2 instance types | GCE machine types |
| Auto Loader (processed-files set) | Auto Loader `cloudFiles` + checkpoint | S3 + SNS/SQS notifications | GCS + Pub/Sub notifications |
| `routers/dlt.py` | Delta Live Tables pipelines | DLT (serverless or classic) | DLT |
| `routers/jobs.py` + APScheduler | Workflows / Jobs scheduler | Jobs (control plane) | Jobs (control plane) |
| local MLflow (sqlite) | Managed MLflow + Registry | MLflow in workspace | MLflow in workspace |
| `.env` values | Cluster env + **secret scopes** | Secrets Manager / SSM | Secret Manager |
| `demo.py` / curl | Notebooks, `databricks` CLI, REST API | same | same |

The biggest conceptual change: **MongoDB metadata is replaced entirely by Unity
Catalog.** You stop managing catalogs/schemas/tables/grants/lineage yourself —
Databricks does it, and lineage becomes automatic.

---

## 1. Workspace deployment

### AWS

A Databricks **account** + one or more **workspaces**. Each workspace's data
plane lives in *your* AWS account.

1. **Databricks account** at accounts.cloud.databricks.com (or via AWS
   Marketplace).
2. **Cross-account IAM role** — Databricks assumes this role to create EC2,
   etc., in your account. Created from the Databricks-provided trust policy.
3. **VPC** — either Databricks-managed or **customer-managed VPC** (recommended
   for prod: your CIDR, subnets across ≥2 AZs, a NAT gateway, and security
   groups).
4. **S3 root (workspace) bucket** — DBFS root + workspace system data.
5. **(Optional) PrivateLink** — keep control-plane ↔ data-plane and user ↔
   workspace traffic off the public internet (front-end + back-end PrivateLink).

Easiest in practice: the **Terraform `databricks` provider** with the
`databricks-workspace-aws` module wires the IAM role, VPC, bucket and workspace.

### GCP

1. **GCP project** with billing enabled; subscribe to Databricks via **GCP
   Marketplace**.
2. **Compute** runs on **GKE** under the hood, managed by Databricks within your
   project.
3. **GCS bucket** for the workspace root storage.
4. **IAM service accounts** — Databricks uses Google service accounts to manage
   GKE/GCE and access GCS; grant the documented roles.
5. **(Optional) Private Service Connect** for private connectivity.

Again, the Terraform `databricks` provider has GCP workspace modules.

---

## 2. Unity Catalog: metastore, storage credentials, external locations

This replaces the demo's MongoDB metastore.

1. **Create one UC metastore per region**, associated with a dedicated storage
   bucket:
   - AWS: an **S3 bucket** + an **IAM role** Databricks assumes to access it.
   - GCP: a **GCS bucket** + a **service account**.
2. **Storage credential** — a UC object wrapping that IAM role (AWS) or service
   account (GCP), so UC can read/write storage on your behalf.
3. **External location** — binds a storage credential to a bucket path
   (`s3://my-bucket/prod` / `gs://my-bucket/prod`). External tables and volumes
   live under external locations; managed tables live in the metastore's managed
   storage.
4. **Create the namespace** to match the demo:

   ```sql
   CREATE CATALOG main MANAGED LOCATION 's3://my-bucket/main';   -- or gs://
   CREATE SCHEMA main.sales;
   ```

5. **Grants** — the demo's `POST /catalog/grants` becomes SQL:

   ```sql
   GRANT USE CATALOG ON CATALOG main TO `data_engineers`;
   GRANT USE SCHEMA  ON SCHEMA  main.sales TO `data_engineers`;
   GRANT SELECT      ON TABLE   main.sales.customers TO `data_engineers`;
   ```

   Principals are users/groups synced from your IdP (SCIM). Lineage is captured
   automatically — no `core/lineage.py` needed.

---

## 3. Compute: clusters & SQL warehouses

Replace the logical clusters in `routers/clusters.py` with real compute.

- **All-purpose / job clusters** — choose instance types:
  - AWS: e.g. `m5d.large`, `i3.xlarge` (local SSD for shuffle), Graviton (`m7g`)
    for price/perf.
  - GCP: e.g. `n2-standard-4`, `n2d` (AMD).
- **Autoscaling** — set `min_workers`/`max_workers` (exactly the demo's fields);
  Databricks adds/removes workers automatically.
- **Photon** — enable it on the cluster/warehouse for vectorised speedups (our
  DuckDB stand-in).
- **Serverless** — prefer serverless SQL warehouses / serverless jobs to avoid
  managing VMs at all.

Provision via the Clusters API, `databricks` CLI, or Terraform
`databricks_cluster` / `databricks_sql_endpoint`. **DBU metering** is automatic
(your `GET /clusters/{n}/usage` becomes the account billing/usage dashboards and
system tables `system.billing.usage`).

---

## 4. Migrating the local Delta tables to cloud object storage

Because delta-rs writes the **real Delta format**, migration is essentially a
file copy — no conversion.

```bash
# Copy each table directory (including _delta_log) to the bucket
aws s3 sync ./data/delta/main/sales/customers  s3://my-bucket/main/sales/customers
# or:  gsutil -m rsync -r ./data/delta/main/sales/customers gs://my-bucket/main/sales/customers
```

Then register it in Unity Catalog:

```sql
-- Managed: copy into a managed location, or
CREATE TABLE main.sales.customers
  USING DELTA LOCATION 's3://my-bucket/main/sales/customers';   -- external table
```

Verify from a Databricks cluster:

```python
spark.read.format("delta").load("s3://my-bucket/main/sales/customers").show()
spark.sql("DESCRIBE HISTORY main.sales.customers")   # time travel survives the copy
```

For large/ongoing migrations use **DEEP CLONE** (`CREATE TABLE ... DEEP CLONE`)
or Auto Loader to re-ingest from source.

---

## 5. Secrets

Stop using `.env`. Use **Databricks secret scopes**, optionally backed by a
cloud secret manager:

```bash
databricks secrets create-scope prod
databricks secrets put-secret prod db_password   # interactive
```

```python
spark.conf.get("...")  # or
dbutils.secrets.get(scope="prod", key="db_password")
```

- AWS: back scopes with **AWS Secrets Manager** / **SSM Parameter Store**; grant
  the cluster instance profile read access.
- GCP: back with **Secret Manager**; grant the cluster service account access.

---

## 6. CI/CD & Infrastructure as Code

- **Databricks Asset Bundles (DABs)** — declare jobs, DLT pipelines, clusters and
  notebooks in `databricks.yml`; deploy per environment:

  ```bash
  databricks bundle validate
  databricks bundle deploy -t prod
  databricks bundle run medallion_job -t prod
  ```

  The demo's `JobCreate` / `DLTPipelineCreate` payloads map directly onto bundle
  `resources.jobs` / `resources.pipelines`.

- **`databricks` CLI** — scriptable access to every workspace API (clusters, jobs,
  secrets, UC, SQL warehouses).
- **Terraform `databricks` provider** — manage the workspace itself plus
  metastores, catalogs, schemas, grants, clusters, warehouses, jobs as code.
  Pair with the AWS/GCP providers for the cloud-account prerequisites.
- **Git folders (Repos)** — sync this repo into the workspace; run notebooks/jobs
  straight from a branch in PRs.

A typical pipeline: PR → `bundle validate` + unit tests on a dev workspace →
merge → `bundle deploy -t staging` → integration tests → `bundle deploy -t prod`.

---

## 7. Networking & security checklist

- Customer-managed VPC/VNet with private subnets; egress via NAT.
- **PrivateLink** (AWS) / **Private Service Connect** (GCP) for front-end and
  back-end traffic.
- IP access lists / SSO (SAML/OIDC) + SCIM group provisioning.
- Unity Catalog for fine-grained `GRANT`s, row/column masks, and audit
  (`system.access.audit`).
- Customer-managed keys (KMS / Cloud KMS) for storage and managed-services
  encryption.
- Cluster policies to constrain instance types, autoscaling bounds, and tags
  (cost control) — the governance the demo's `ClusterCreate` validation hints at.

---

## 8. What you delete from this repo after promotion

| Local component | Replaced by |
|---|---|
| `core/catalog.py` (MongoDB) + `core/metastore.py` | Unity Catalog |
| `core/lineage.py` | Unity Catalog automatic lineage |
| `core/engine.py` DBU metering | Account usage dashboards / `system.billing` |
| `routers/clusters.py` | Clusters / SQL Warehouses APIs |
| `routers/autoloader.py` | Auto Loader (`cloudFiles`) |
| `routers/dlt.py` | Delta Live Tables |
| `routers/jobs.py` + APScheduler | Workflows / Jobs |
| local MLflow sqlite | Managed MLflow |
| **`core/delta_io.py` (Delta tables)** | **kept conceptually** — the format is identical; just point at S3/GCS |

The Delta tables themselves are the one thing you carry over unchanged — which is
the whole point of an open Lakehouse format.
