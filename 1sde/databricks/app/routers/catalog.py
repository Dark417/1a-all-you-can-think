"""Unity Catalog -- the unified governance layer.

Unity Catalog gives Databricks a true **three-level namespace**
``catalog.schema.table`` (replacing the old 2-level Hive metastore), centralised
**grants** on securables (catalog / schema / table), and automatic **lineage**.

This router manages the catalog/schema namespace, registers tables, and handles
grants + effective-privilege resolution. (Lineage lives in the ``governance``
router; Delta DDL/DML lives in the ``delta`` router.)
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core.catalog import Collections, get_db
from ..core.delta_io import describe_detail, table_exists
from ..core.engine import utcnow
from ..core.naming import normalize_fqn, parse_fqn
from ..models import CatalogCreate, GrantRequest, RevokeRequest, SchemaCreate

router = APIRouter(prefix="/catalog", tags=["2. Unity Catalog"])


# --------------------------------------------------------------------------- #
# Namespace: catalogs & schemas
# --------------------------------------------------------------------------- #
@router.post("/catalogs", summary="CREATE CATALOG")
def create_catalog(body: CatalogCreate):
    db = get_db()
    name = body.name.lower()
    if db[Collections.CATALOGS].find_one({"_id": name}):
        raise HTTPException(409, f"Catalog '{name}' already exists.")
    db[Collections.CATALOGS].insert_one(
        {"_id": name, "comment": body.comment, "created_at": utcnow()}
    )
    # Every catalog gets a 'default' schema, like Unity Catalog.
    _ensure_schema(name, "default", "default schema")
    return {"status": "created", "catalog": name}


@router.get("/catalogs", summary="SHOW CATALOGS")
def list_catalogs():
    return [
        {"name": c["_id"], "comment": c.get("comment")}
        for c in get_db()[Collections.CATALOGS].find()
    ]


@router.post("/schemas", summary="CREATE SCHEMA")
def create_schema(body: SchemaCreate):
    db = get_db()
    cat = body.catalog.lower()
    if not db[Collections.CATALOGS].find_one({"_id": cat}):
        raise HTTPException(404, f"Catalog '{cat}' does not exist.")
    sid = f"{cat}.{body.name.lower()}"
    if db[Collections.SCHEMAS].find_one({"_id": sid}):
        raise HTTPException(409, f"Schema '{sid}' already exists.")
    _ensure_schema(cat, body.name.lower(), body.comment)
    return {"status": "created", "schema": sid}


@router.get("/{catalog}/schemas", summary="SHOW SCHEMAS")
def list_schemas(catalog: str):
    return [
        {"name": s["name"], "comment": s.get("comment")}
        for s in get_db()[Collections.SCHEMAS].find({"catalog": catalog.lower()})
    ]


@router.get("/tables", summary="SHOW TABLES (across the metastore)")
def list_tables():
    return [
        {
            "name": t["_id"],
            "catalog": t["catalog"],
            "schema": t["schema"],
            "kind": t.get("kind", "MANAGED"),
            "columns": t.get("columns", []),
        }
        for t in get_db()[Collections.TABLES].find()
    ]


@router.get("/tables/{fqn}/describe", summary="DESCRIBE TABLE (metadata + Delta detail)")
def describe(fqn: str):
    fqn = normalize_fqn(fqn)
    meta = get_db()[Collections.TABLES].find_one({"_id": fqn})
    if not meta:
        raise HTTPException(404, f"Table '{fqn}' is not registered in Unity Catalog.")
    out = {
        "table": fqn,
        "catalog": meta["catalog"],
        "schema": meta["schema"],
        "columns": meta.get("columns", []),
        "kind": meta.get("kind", "MANAGED"),
    }
    if table_exists(fqn):
        out["delta_detail"] = describe_detail(fqn)
    return out


# --------------------------------------------------------------------------- #
# Governance: grants on securables
# --------------------------------------------------------------------------- #
@router.post("/grants", summary="GRANT <privilege> ON <securable> TO <principal>")
def grant(body: GrantRequest):
    get_db()[Collections.GRANTS].update_one(
        {
            "privilege": body.privilege.upper(),
            "securable_type": body.securable_type.upper(),
            "securable_name": normalize_securable(body.securable_type, body.securable_name),
            "principal": body.principal,
        },
        {"$set": {"at": utcnow()}},
        upsert=True,
    )
    return {"status": "granted", **body.model_dump()}


@router.post("/revoke", summary="REVOKE <privilege> ON <securable> FROM <principal>")
def revoke(body: RevokeRequest):
    res = get_db()[Collections.GRANTS].delete_one(
        {
            "privilege": body.privilege.upper(),
            "securable_type": body.securable_type.upper(),
            "securable_name": normalize_securable(body.securable_type, body.securable_name),
            "principal": body.principal,
        }
    )
    return {"status": "revoked", "removed": res.deleted_count, **body.model_dump()}


@router.get("/grants", summary="SHOW GRANTS (all)")
def list_grants():
    return [
        {
            "privilege": g["privilege"],
            "securable_type": g["securable_type"],
            "securable_name": g["securable_name"],
            "principal": g["principal"],
        }
        for g in get_db()[Collections.GRANTS].find()
    ]


@router.get("/effective-privileges", summary="Resolve effective privileges on a table")
def effective_privileges(table: str, principal: str):
    """A grant on a parent securable cascades to children: USE_CATALOG on
    ``main`` and USE_SCHEMA on ``main.sales`` plus SELECT on
    ``main.sales.customers`` together let a principal read the table. We union
    the grants that apply at the catalog, schema and table level for this
    principal -- exactly how Unity Catalog resolves access."""
    cat, schema, _ = parse_fqn(table)
    fqn = normalize_fqn(table)
    securables = {cat, f"{cat}.{schema}", fqn}
    db = get_db()
    privs = []
    for g in db[Collections.GRANTS].find({"principal": principal}):
        if g["securable_name"] in securables:
            privs.append(
                {
                    "privilege": g["privilege"],
                    "on_type": g["securable_type"],
                    "on_name": g["securable_name"],
                }
            )
    can_read = any(p["privilege"] in {"SELECT", "ALL_PRIVILEGES"} for p in privs)
    return {
        "table": fqn,
        "principal": principal,
        "applicable_securables": sorted(securables),
        "privileges": privs,
        "can_select": can_read,
    }


# --------------------------------------------------------------------------- #
def normalize_securable(securable_type: str, name: str) -> str:
    """Lower-case + canonicalise a securable name by its type."""
    if securable_type.upper() == "TABLE":
        return normalize_fqn(name)
    return name.lower()


def _ensure_schema(catalog: str, schema: str, comment: str | None) -> None:
    sid = f"{catalog}.{schema}"
    get_db()[Collections.SCHEMAS].update_one(
        {"_id": sid},
        {
            "$setOnInsert": {
                "_id": sid,
                "catalog": catalog,
                "name": schema,
                "comment": comment,
                "created_at": utcnow(),
            }
        },
        upsert=True,
    )
