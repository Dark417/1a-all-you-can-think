"""MLlib: a complete DataFrame-based machine-learning pipeline.

The Pipeline API chains Transformers and Estimators so the exact same feature
engineering is applied at train and serve time. Here we build a binary
classifier predicting whether a person is "senior" (age >= 45) from simple
features — small and deterministic enough to assert on in a test.

Stages:
  StringIndexer  (city -> index)         Transformer-producing Estimator
  OneHotEncoder  (index -> sparse vec)   Transformer-producing Estimator
  VectorAssembler(features -> vector)    Transformer
  LogisticRegression                     Estimator -> Model
"""
from __future__ import annotations

from pyspark.ml import Pipeline, PipelineModel
from pyspark.ml.classification import LogisticRegression
from pyspark.ml.evaluation import BinaryClassificationEvaluator
from pyspark.ml.feature import OneHotEncoder, StringIndexer, VectorAssembler
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F


def labeled_people(spark: SparkSession) -> DataFrame:
    """Synthetic dataset with a clear age -> label signal."""
    rows = [
        ("NYC", 25), ("NYC", 30), ("NYC", 48), ("NYC", 55),
        ("SF", 22), ("SF", 35), ("SF", 50), ("SF", 60),
        ("LA", 28), ("LA", 41), ("LA", 46), ("LA", 52),
    ]
    df = spark.createDataFrame(rows, ["city", "age"])
    return df.withColumn("label", (F.col("age") >= 45).cast("double"))


def build_pipeline() -> Pipeline:
    """Assemble the feature + model pipeline (unfitted)."""
    indexer = StringIndexer(inputCol="city", outputCol="city_idx", handleInvalid="keep")
    encoder = OneHotEncoder(inputCols=["city_idx"], outputCols=["city_vec"])
    assembler = VectorAssembler(inputCols=["age", "city_vec"], outputCol="features")
    lr = LogisticRegression(featuresCol="features", labelCol="label", maxIter=20)
    return Pipeline(stages=[indexer, encoder, assembler, lr])


def train_and_evaluate(df: DataFrame) -> dict:
    """Split, fit the pipeline, score the test set, and return metrics."""
    train, test = df.randomSplit([0.7, 0.3], seed=42)
    model: PipelineModel = build_pipeline().fit(train)

    predictions = model.transform(test)
    evaluator = BinaryClassificationEvaluator(
        labelCol="label", metricName="areaUnderROC"
    )
    # Guard against a degenerate split (all one class) in tiny data.
    auc = evaluator.evaluate(predictions) if predictions.count() else float("nan")

    return {
        "n_train": train.count(),
        "n_test": test.count(),
        "auc": auc,
        "model": model,
    }
