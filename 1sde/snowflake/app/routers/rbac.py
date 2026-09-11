"""Role-Based Access Control.

Snowflake security is role-centric: privileges are granted to *roles*, roles
are granted to users (and to other roles, forming a hierarchy). Access is the
union of the privileges of a user's active role and everything beneath it.
System roles: ACCOUNTADMIN > SECURITYADMIN/SYSADMIN > custom roles > PUBLIC.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..core.catalog import Collections, get_db
from ..core.engine import utcnow
from ..models import GrantRequest, RoleCreate, RoleGrant, UserCreate

router = APIRouter(prefix="/rbac", tags=["9. RBAC (roles, users, grants)"])

SYSTEM_ROLES = ["ACCOUNTADMIN", "SECURITYADMIN", "SYSADMIN", "PUBLIC"]


@router.post("/bootstrap", summary="Create built-in system roles")
def bootstrap():
    db = get_db()
    for r in SYSTEM_ROLES:
        db[Collections.ROLES].update_one(
            {"_id": r}, {"$setOnInsert": {"_id": r, "system": True, "granted_roles": []}}, upsert=True
        )
    # ACCOUNTADMIN inherits everything.
    db[Collections.ROLES].update_one(
        {"_id": "ACCOUNTADMIN"}, {"$set": {"granted_roles": ["SYSADMIN", "SECURITYADMIN"]}}
    )
    db[Collections.ROLES].update_one({"_id": "SYSADMIN"}, {"$set": {"granted_roles": ["PUBLIC"]}})
    return {"status": "bootstrapped", "roles": SYSTEM_ROLES}


@router.post("/roles", summary="CREATE ROLE")
def create_role(body: RoleCreate):
    db = get_db()
    if db[Collections.ROLES].find_one({"_id": body.name}):
        raise HTTPException(409, "Role exists")
    db[Collections.ROLES].insert_one({"_id": body.name, "system": False, "granted_roles": []})
    return {"status": "created", "role": body.name}


@router.post("/users", summary="CREATE USER")
def create_user(body: UserCreate):
    db = get_db()
    if db[Collections.USERS].find_one({"_id": body.name}):
        raise HTTPException(409, "User exists")
    db[Collections.USERS].insert_one(
        {"_id": body.name, "default_role": body.default_role, "roles": [body.default_role], "created_at": utcnow()}
    )
    return {"status": "created", "user": body.name}


@router.post("/grants", summary="GRANT <privilege> ON <object> TO ROLE")
def grant_privilege(body: GrantRequest):
    if not get_db()[Collections.ROLES].find_one({"_id": body.to_role}):
        raise HTTPException(404, f"Role '{body.to_role}' not found")
    get_db()[Collections.GRANTS].insert_one(
        {
            "privilege": body.privilege.upper(),
            "on_type": body.on_type.upper(),
            "on_name": body.on_name,
            "role": body.to_role,
            "at": utcnow(),
        }
    )
    return {"status": "granted", **body.model_dump()}


@router.post("/grants/role", summary="GRANT ROLE <r> TO ROLE|USER")
def grant_role(body: RoleGrant):
    db = get_db()
    if body.to_type == "ROLE":
        if not db[Collections.ROLES].find_one({"_id": body.to}):
            raise HTTPException(404, "Target role not found")
        db[Collections.ROLES].update_one({"_id": body.to}, {"$addToSet": {"granted_roles": body.role}})
    else:
        if not db[Collections.USERS].find_one({"_id": body.to}):
            raise HTTPException(404, "Target user not found")
        db[Collections.USERS].update_one({"_id": body.to}, {"$addToSet": {"roles": body.role}})
    return {"status": "granted", "role": body.role, "to": body.to, "to_type": body.to_type}


@router.get("/roles/{role}/effective-privileges", summary="Resolve inherited privileges")
def effective_privileges(role: str):
    """Walk the role hierarchy and union all privileges -- exactly how Snowflake
    decides whether an operation is allowed."""
    db = get_db()
    seen: set[str] = set()
    stack = [role]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        r = db[Collections.ROLES].find_one({"_id": cur})
        if r:
            stack.extend(r.get("granted_roles", []))
    privs = list(db[Collections.GRANTS].find({"role": {"$in": list(seen)}}, {"_id": 0, "at": 0}))
    return {"role": role, "inherited_roles": sorted(seen), "privileges": privs}


@router.get("/check", summary="Would ROLE be allowed PRIVILEGE on OBJECT?")
def check(role: str, privilege: str, on_name: str):
    eff = effective_privileges(role)["privileges"]
    allowed = any(
        g["on_name"] == on_name and g["privilege"] in {privilege.upper(), "ALL"} for g in eff
    )
    return {"role": role, "privilege": privilege.upper(), "on_name": on_name, "allowed": allowed}
