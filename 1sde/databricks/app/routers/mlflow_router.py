"""MLflow -- experiment tracking + the Model Registry.

Databricks bundles a managed **MLflow** for the full ML lifecycle: log
experiments/runs (params, metrics, tags, artifacts), then register models to the
**Model Registry** and promote versions through stages (Staging -> Production).

This router drives a **real local MLflow** (sqlite tracking backend under
``MLRUNS_DIR`` -- the file store is in maintenance mode in MLflow 3.x). To keep
deps light we log a trivial ``pyfunc`` model (no sklearn) so registration and
stage transitions genuinely work and show up in the registry.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..models import ExperimentCreate, RunLog, TransitionStage

router = APIRouter(prefix="/mlflow", tags=["10. MLflow & Model Registry"])


def _client():
    """Configure MLflow against the local sqlite store and return a client.

    Done lazily (per call) so the hermetic env vars set by demo/tests apply.
    """
    import mlflow
    from mlflow.tracking import MlflowClient

    from ..core.config import get_settings

    settings = get_settings()
    mlflow.set_tracking_uri(settings.mlflow_tracking_uri)
    mlflow.set_registry_uri(settings.mlflow_tracking_uri)
    return mlflow, MlflowClient()


def _trivial_model():
    """A dependency-free pyfunc model (no sklearn): predicts a constant per row.

    Built lazily so ``mlflow.pyfunc.PythonModel`` is only imported when needed.
    """
    from mlflow.pyfunc import PythonModel

    class TrivialModel(PythonModel):
        def predict(self, context, model_input, params=None):  # noqa: ANN001
            try:
                n = len(model_input)
            except TypeError:
                n = 1
            return [0] * n

    return TrivialModel()


@router.post("/experiments", summary="Create an MLflow experiment")
def create_experiment(body: ExperimentCreate):
    mlflow, client = _client()
    from ..core.config import get_settings

    existing = client.get_experiment_by_name(body.name)
    if existing:
        return {"status": "exists", "experiment": body.name, "experiment_id": existing.experiment_id}
    exp_id = mlflow.create_experiment(
        body.name, artifact_location=get_settings().mlflow_artifact_root + "/" + body.name
    )
    return {"status": "created", "experiment": body.name, "experiment_id": exp_id}


@router.post("/runs", summary="Start a run: log params/metrics/tags (and optionally register a model)")
def log_run(body: RunLog):
    mlflow, client = _client()
    from ..core.config import get_settings

    if client.get_experiment_by_name(body.experiment) is None:
        mlflow.create_experiment(
            body.experiment,
            artifact_location=get_settings().mlflow_artifact_root + "/" + body.experiment,
        )
    mlflow.set_experiment(body.experiment)

    registered = None
    with mlflow.start_run(run_name=body.run_name) as run:
        for k, v in body.params.items():
            mlflow.log_param(k, v)
        for k, v in body.metrics.items():
            mlflow.log_metric(k, float(v))
        for k, v in body.tags.items():
            mlflow.set_tag(k, v)
        run_id = run.info.run_id

        if body.register_as:
            info = mlflow.pyfunc.log_model(
                name="model",
                python_model=_trivial_model(),
                registered_model_name=body.register_as,
            )
            versions = client.search_model_versions(f"name='{body.register_as}'")
            latest = max(int(v.version) for v in versions)
            registered = {"model": body.register_as, "version": latest, "model_uri": info.model_uri}

    return {
        "status": "logged",
        "experiment": body.experiment,
        "run_id": run_id,
        "params": body.params,
        "metrics": body.metrics,
        "registered_model": registered,
    }


@router.get("/runs", summary="List runs for an experiment")
def list_runs(experiment: str):
    mlflow, client = _client()
    exp = client.get_experiment_by_name(experiment)
    if exp is None:
        raise HTTPException(404, f"Experiment '{experiment}' not found")
    runs = client.search_runs([exp.experiment_id])
    return {
        "experiment": experiment,
        "run_count": len(runs),
        "runs": [
            {
                "run_id": r.info.run_id,
                "run_name": r.data.tags.get("mlflow.runName"),
                "status": r.info.status,
                "params": dict(r.data.params),
                "metrics": dict(r.data.metrics),
            }
            for r in runs
        ],
    }


@router.get("/models", summary="List registered models + their versions/stages")
def list_models():
    _mlflow, client = _client()
    out = []
    for m in client.search_registered_models():
        versions = client.search_model_versions(f"name='{m.name}'")
        out.append(
            {
                "name": m.name,
                "versions": [
                    {"version": int(v.version), "stage": v.current_stage, "status": v.status}
                    for v in versions
                ],
            }
        )
    return {"registered_models": out}


@router.post("/models/transition", summary="Transition a model version to a stage")
def transition(body: TransitionStage):
    _mlflow, client = _client()
    try:
        mv = client.transition_model_version_stage(body.model, str(body.version), body.stage)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(404, str(exc))
    return {
        "status": "transitioned",
        "model": body.model,
        "version": int(mv.version),
        "stage": mv.current_stage,
    }
