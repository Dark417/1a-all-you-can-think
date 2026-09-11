"""Unity Catalog **data lineage** -- table -> table edges.

Unity Catalog automatically captures lineage: which tables (and columns) were
read to produce which other tables, across notebooks, jobs and pipelines. We
record a lineage edge whenever one table is derived from another (medallion
Bronze->Silver->Gold, DLT steps, CTAS, etc.) and expose the resulting graph.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .catalog import Collections, get_db
from .naming import normalize_fqn


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def record_edge(source: str, target: str, operation: str) -> None:
    """Record that ``target`` was produced from ``source`` via ``operation``.

    Idempotent on (source, target, operation) so re-running a pipeline does not
    create duplicate edges. The ``source`` may be a non-table node (e.g. a
    ``stage:...`` landing dir for Auto Loader), in which case it is kept as-is.
    """
    src = _node(source)
    tgt = normalize_fqn(target)
    get_db()[Collections.LINEAGE].update_one(
        {"source": src, "target": tgt, "operation": operation},
        {"$set": {"source": src, "target": tgt, "operation": operation, "at": utcnow()}},
        upsert=True,
    )


def _node(name: str) -> str:
    """Normalise a lineage node: real tables -> canonical FQN; external sources
    (``stage:...``, ``file:...``) are kept verbatim."""
    if ":" in name:
        return name
    return normalize_fqn(name)


def record_edges(sources: list[str], target: str, operation: str) -> None:
    for s in sources:
        record_edge(s, target, operation)


def graph() -> dict:
    """Return the full lineage graph: distinct nodes + edges."""
    edges = []
    nodes: set[str] = set()
    for e in get_db()[Collections.LINEAGE].find({}, {"_id": 0}):
        edges.append(
            {"source": e["source"], "target": e["target"], "operation": e["operation"]}
        )
        nodes.add(e["source"])
        nodes.add(e["target"])
    return {"nodes": sorted(nodes), "edges": edges}


def upstream(fqn: str) -> list[str]:
    """All tables transitively upstream of ``fqn`` (its data sources)."""
    target = normalize_fqn(fqn)
    db = get_db()
    seen: set[str] = set()
    stack = [target]
    while stack:
        cur = stack.pop()
        for e in db[Collections.LINEAGE].find({"target": cur}):
            if e["source"] not in seen:
                seen.add(e["source"])
                stack.append(e["source"])
    return sorted(seen)
