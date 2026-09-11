"""UDFs & Stored Procedures.

Snowflake lets you extend SQL with SQL UDFs, Python UDFs (Snowpark), and stored
procedures. DuckDB lets us register real Python functions, so Python UDFs here
actually execute. SQL UDFs are inlined into queries.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from ..core.catalog import Collections, get_db
from ..core.engine import get_engine, utcnow
from ..models import FunctionCreate

router = APIRouter(prefix="/functions", tags=["10. UDFs & Stored Procedures"])

_DUCK_TYPES = {"DOUBLE": "DOUBLE", "NUMBER": "DOUBLE", "INT": "BIGINT", "INTEGER": "BIGINT", "STRING": "VARCHAR", "VARCHAR": "VARCHAR", "BOOLEAN": "BOOLEAN"}


@router.post("", summary="CREATE FUNCTION / PROCEDURE")
def create_function(body: FunctionCreate):
    db = get_db()
    if db[Collections.FUNCTIONS].find_one({"_id": body.name}):
        raise HTTPException(409, "Function exists")
    eng = get_engine()

    if body.kind == "UDF_PYTHON":
        _register_python_udf(eng, body)
    elif body.kind == "UDF_SQL":
        args = ", ".join(f'"{a.name}" {_DUCK_TYPES.get(a.type.upper(), a.type)}' for a in body.args)
        ret = _DUCK_TYPES.get(body.returns.upper(), body.returns)
        eng.con.execute(f'CREATE OR REPLACE MACRO "{body.name}"({_macro_args(body)}) AS ({body.body})')

    db[Collections.FUNCTIONS].insert_one(
        {
            "_id": body.name,
            "kind": body.kind,
            "args": [a.model_dump() for a in body.args],
            "returns": body.returns,
            "body": body.body,
            "created_at": utcnow(),
        }
    )
    return {"status": "created", "function": body.name, "kind": body.kind}


@router.get("", summary="SHOW USER FUNCTIONS")
def list_functions():
    return [
        {"name": f["_id"], "kind": f["kind"], "returns": f["returns"], "args": f["args"]}
        for f in get_db()[Collections.FUNCTIONS].find()
    ]


@router.post("/{name}/call", summary="Call a function with positional args")
def call(
    name: str,
    args: list[Any] = Body(default=[], examples=[[100.0]]),
    warehouse: str = "COMPUTE_WH",
):
    fn = get_db()[Collections.FUNCTIONS].find_one({"_id": name})
    if not fn:
        raise HTTPException(404, "Function not found")
    placeholders = ", ".join("?" for _ in args)
    sql = f'SELECT "{name}"({placeholders}) AS result'
    try:
        res = get_engine().run(sql, warehouse=warehouse, params=args, use_cache=False)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
    return {"function": name, "args": args, "result": res["rows"][0][0] if res["rows"] else None}


# --------------------------------------------------------------------------- #
def _macro_args(body: FunctionCreate) -> str:
    return ", ".join(f'"{a.name}"' for a in body.args)


_DUCK_TYPING = {
    "DOUBLE": "DOUBLE", "NUMBER": "DOUBLE", "FLOAT": "FLOAT",
    "INT": "BIGINT", "INTEGER": "BIGINT", "BIGINT": "BIGINT",
    "STRING": "VARCHAR", "VARCHAR": "VARCHAR", "BOOLEAN": "BOOLEAN",
}


def _register_python_udf(eng, body: FunctionCreate) -> None:
    """Exec the Python body to obtain a callable named like the function and
    register it with DuckDB (with explicit types) so it runs inside SQL."""
    ns: dict = {}
    exec(body.body, ns)  # noqa: S102 - intentional: this is the UDF definition
    func = ns.get(body.name) or next((v for v in ns.values() if callable(v)), None)
    if func is None:
        raise HTTPException(400, "Python UDF body must define a callable.")
    try:
        eng.con.remove_function(body.name)
    except Exception:  # noqa: BLE001
        pass
    params = [_DUCK_TYPING.get(a.type.upper(), "VARCHAR") for a in body.args]
    return_type = _DUCK_TYPING.get(body.returns.upper(), "VARCHAR")
    eng.con.create_function(body.name, func, params, return_type)
