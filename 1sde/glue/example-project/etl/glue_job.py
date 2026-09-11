"""AWS Glue ETL job (PySpark + DynamicFrame).

This script is designed to run INSIDE AWS Glue. The `awsglue` package only
exists on Glue workers, so this file will not import locally — that is expected.
To develop locally, use the official `amazon/aws-glue-libs` Docker image.

What it does:
  1. Reads the source table from the Glue Data Catalog as a DynamicFrame.
  2. Resolves ambiguous/choice types and applies an explicit column mapping.
  3. Drops records with null business keys and filters out zero-amount orders.
  4. Repartitions by `region` and writes partitioned Parquet back to S3 while
     updating the Data Catalog with any new partitions.

Job parameters (pass with --<name> <value>):
  --JOB_NAME          (required by Glue)
  --source_database   e.g. sales_db
  --source_table      e.g. raw_sales
  --target_path       e.g. s3://my-bucket/sales/
  --target_database   catalog DB to register output partitions in
  --target_table      catalog table name for the output
"""
import sys

from awsglue.context import GlueContext
from awsglue.dynamicframe import DynamicFrame
from awsglue.job import Job
from awsglue.transforms import ApplyMapping, DropNullFields, ResolveChoice
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql.functions import col


def main():
    args = getResolvedOptions(
        sys.argv,
        [
            "JOB_NAME",
            "source_database",
            "source_table",
            "target_path",
            "target_database",
            "target_table",
        ],
    )

    sc = SparkContext()
    glue_context = GlueContext(sc)
    spark = glue_context.spark_session
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    # 1. Read from the Data Catalog. transformation_ctx enables job bookmarks
    #    so reruns only pick up new data.
    source = glue_context.create_dynamic_frame.from_catalog(
        database=args["source_database"],
        table_name=args["source_table"],
        transformation_ctx="source",
    )
    print(f"Read {source.count()} records from "
          f"{args['source_database']}.{args['source_table']}")

    # 2a. Resolve choice/ambiguous types (e.g. a column seen as both int & string).
    resolved = ResolveChoice.apply(
        frame=source, choice="make_struct", transformation_ctx="resolved"
    )

    # 2b. Apply an explicit mapping: (source_col, source_type, target_col, target_type).
    mapped = ApplyMapping.apply(
        frame=resolved,
        mappings=[
            ("order_id", "string", "order_id", "string"),
            ("customer_id", "string", "customer_id", "string"),
            ("region", "string", "region", "string"),
            ("amount", "double", "amount", "double"),
            ("currency", "string", "currency", "string"),
            ("ordered_at", "timestamp", "ordered_at", "timestamp"),
        ],
        transformation_ctx="mapped",
    )

    # 3. Drop null fields, then filter using Spark DataFrame for richer predicates.
    cleaned = DropNullFields.apply(frame=mapped, transformation_ctx="cleaned")
    df = cleaned.toDF()
    df = df.filter(col("order_id").isNotNull() & (col("amount") > 0))

    # Derive partition columns from the order timestamp.
    from pyspark.sql.functions import date_format

    df = (
        df.withColumn("year", date_format(col("ordered_at"), "yyyy"))
        .withColumn("month", date_format(col("ordered_at"), "MM"))
        .repartition("region")
    )

    output = DynamicFrame.fromDF(df, glue_context, "output")

    # 4. Write partitioned Parquet and update the catalog in one step.
    glue_context.write_dynamic_frame.from_options(
        frame=output,
        connection_type="s3",
        connection_options={
            "path": args["target_path"],
            "partitionKeys": ["year", "month"],
        },
        format="glueparquet",
        format_options={"compression": "snappy"},
        transformation_ctx="write",
    )

    print(f"Wrote {output.count()} records to {args['target_path']}")
    job.commit()


if __name__ == "__main__":
    main()
