"""Delta Live Tables (DLT) -- declarative pipelines with data quality.

In Databricks you declare a pipeline as a set of ``@dlt.table`` functions; DLT
works out the **dependency DAG**, materialises each table, and enforces
**expectations** (data-quality constraints):

  * ``@dlt.expect``                -> WARN: keep violating rows, just report them.
  * ``@dlt.expect_or_drop``        -> DROP: quarantine (drop) violating rows.
  * ``@dlt.expect_or_fail``        -> FAIL: abort the update on any violation.

Here a pipeline is a list of steps (name + SQL + depends_on + expectations). We
topologically sort the steps, run each on DuckDB over the upstream Delta tables,
apply expectations, write the result as a Delta table, and return a per-step,
per-expectation quality report (rows passed / failed / quarantined).
"""
from __future__ import annotations

import polars as pl
from fastapi import APIRouter, HTTPException

from ..core import delta_io
from ..core.catalog import Collections, get_db
from ..core.engine import get_engine, utcnow
from ..core.lineage import record_edge
from ..core.metastore import register_table
from ..core.naming import normalize_fqn
from ..models import DLTPipelineCreate, DLTRunRequest

router = APIRouter(prefix="/dlt", tags=["7. Delta Live Tables"])


@router.post("", summary="Create (define) a DLT pipeline")
def create_pipeline(body: DLTPipelineCreate):
    db = get_db()
    if db[Collections.DLT_PIPELINES].find_one({"_id": body.name}):
        raise HTTPException(409, f"Pipeline '{body.name}' already exists.")
    keys = {s.name for s in body.steps}
    for s in body.steps:
        for dep in s.depends_on:
            if dep not in keys:
                raise HTTPException(400, f"Step '{s.name}' depends on unknown step '{dep}'.")
    db[Collections.DLT_PIPELINES].insert_one(
        {
            "_id": body.name,
            "target_catalog": body.target_catalog.lower(),
            "target_schema": body.target_schema.lower(),
            "steps": [s.model_dump() for s in body.steps],
            "last_run": None,
            "created_at": utcnow(),
        }
    )
    return {"status": "created", "pipeline": body.name, "steps": [s.name for s in body.steps]}


@router.get("", summary="List DLT pipelines")
def list_pipelines():
    return [
        {"name": p["_id"], "steps": [s["name"] for s in p["steps"]]}
        for p in get_db()[Collections.DLT_PIPELINES].find()
    ]


@router.post("/{name}/run", summary="Run the pipeline DAG (with expectations)")
def run_pipeline(name: str, body: DLTRunRequest):
    db = get_db()
    pipe = db[Collections.DLT_PIPELINES].find_one({"_id": name})
    if not pipe:
        raise HTTPException(404, "Pipeline not found")

    steps = {s["name"]: s for s in pipe["steps"]}
    order = _toposort(steps)
    eng = get_engine()
    target_prefix = f"{pipe['target_catalog']}.{pipe['target_schema']}"

    report = []
    for step_name in order:
        step = steps[step_name]
        target_fqn = f"{target_prefix}.{step_name}"

        # Make upstream step tables queryable as their *step name* (so the step
        # SQL can simply `SELECT ... FROM <upstream_step>`).
        for dep in step["depends_on"]:
            dep_fqn = f"{target_prefix}.{dep}"
            view = eng.register_delta(dep_fqn)
            eng.con.execute(f"CREATE OR REPLACE VIEW {dep} AS SELECT * FROM {view}")

        # Materialise the step query.
        res = eng.run(step["query"], cluster=body.cluster, use_cache=False)
        df = pl.DataFrame(
            {col: [r[i] for r in res["rows"]] for i, col in enumerate(res["columns"])}
        ) if res["columns"] else pl.DataFrame()

        # Apply expectations.
        exp_report, kept = _apply_expectations(eng, df, step.get("expectations", []))

        delta_io.create_or_overwrite(target_fqn, kept.to_arrow())
        register_table(target_fqn, kind="MANAGED")
        for dep in step["depends_on"]:
            record_edge(f"{target_prefix}.{dep}", target_fqn, "dlt")

        report.append(
            {
                "step": step_name,
                "table": normalize_fqn(target_fqn),
                "rows_in": df.height,
                "rows_written": kept.height,
                "expectations": exp_report,
            }
        )

    db[Collections.DLT_PIPELINES].update_one(
        {"_id": name}, {"$set": {"last_run": utcnow()}}
    )
    return {"status": "completed", "pipeline": name, "run_order": order, "report": report}


# --------------------------------------------------------------------------- #
def _apply_expectations(eng, df: pl.DataFrame, expectations: list[dict]):
    """Evaluate each expectation's SQL constraint over ``df`` and act on it."""
    reports = []
    kept = df
    for exp in expectations:
        if kept.height == 0:
            reports.append({**_exp_meta(exp), "passed": 0, "failed": 0})
            continue
        # Evaluate the boolean constraint per row using DuckDB.
        eng.con.register("_dlt_df", kept.to_arrow())
        flags = eng.con.execute(
            f"SELECT ({exp['constraint']}) AS ok FROM _dlt_df"
        ).fetchall()
        eng.con.unregister("_dlt_df")
        mask = [bool(f[0]) for f in flags]
        failed = mask.count(False)
        passed = mask.count(True)

        if exp["action"] == "FAIL" and failed:
            raise HTTPException(
                422,
                f"Expectation '{exp['name']}' failed for {failed} row(s); pipeline aborted (expect_or_fail).",
            )
        if exp["action"] == "DROP":
            kept = kept.filter(pl.Series(mask))  # quarantine: keep only passing rows
        reports.append(
            {**_exp_meta(exp), "passed": passed, "failed": failed,
             "quarantined": failed if exp["action"] == "DROP" else 0}
        )
    return reports, kept


def _exp_meta(exp: dict) -> dict:
    return {"name": exp["name"], "constraint": exp["constraint"], "action": exp["action"]}


def _toposort(steps: dict) -> list[str]:
    order: list[str] = []
    visited: set[str] = set()
    temp: set[str] = set()

    def visit(n: str):
        if n in visited:
            return
        if n in temp:
            raise HTTPException(400, f"Cycle detected at step '{n}'.")
        temp.add(n)
        for dep in steps[n]["depends_on"]:
            visit(dep)
        temp.discard(n)
        visited.add(n)
        order.append(n)

    for n in steps:
        visit(n)
    return order
