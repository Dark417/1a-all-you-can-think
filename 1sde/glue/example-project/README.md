# Glue Catalog Example Project (Python)

A small, runnable project showing how to manage the **AWS Glue Data Catalog**
with `boto3` and how to write a **Glue PySpark ETL job**.

```
example-project/
├── README.md
├── requirements.txt
├── config.py                  # central config (bucket, db, table names)
├── catalog/
│   ├── __init__.py
│   ├── client.py              # thin boto3 Glue client factory
│   ├── database.py            # create / list / delete databases
│   ├── table.py               # create partitioned table with schema
│   └── partitions.py          # batch add / list partitions
├── etl/
│   └── glue_job.py            # Glue ETL job (DynamicFrame, runs in Glue)
├── scripts/
│   └── bootstrap_catalog.py   # end-to-end: db -> table -> partitions
└── tests/
    └── test_catalog.py        # pytest + moto (mocked AWS, runs offline)
```

## Prerequisites

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run the offline tests (no AWS needed)

`moto` mocks the Glue API in-process, so the catalog logic is fully testable
without an AWS account:

```bash
pytest -q
```

## Run against real AWS

Configure credentials (`aws configure` or env vars) and a region, then:

```bash
export GLUE_BUCKET=my-data-bucket          # an S3 bucket you own
export GLUE_DATABASE=sales_db
python scripts/bootstrap_catalog.py
```

This creates `sales_db`, a partitioned `sales` table, and a few partitions.
You can then query it in Athena:

```sql
SELECT region, SUM(amount) AS total
FROM sales_db.sales
WHERE year = '2024' AND month = '01'
GROUP BY region;
```

## The ETL job

`etl/glue_job.py` is written to run **inside AWS Glue** (it imports
`awsglue.*`, which only exists on Glue workers). Upload it as a Glue job script
and pass `--JOB_NAME`, `--source_database`, `--source_table`, and
`--target_path`. It reads from the catalog as a DynamicFrame, applies a mapping,
filters nulls, repartitions by `region`, and writes partitioned Parquet while
updating the catalog.
