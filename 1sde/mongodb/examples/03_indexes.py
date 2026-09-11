"""
03_indexes.py — MongoDB Index Types and explain() with PyMongo
==============================================================

Covers:
  * Single-field ascending/descending indexes
  * Compound index (multi-field)
  * Unique index (enforce uniqueness constraint)
  * Text index (full-text search with $text / $search)
  * TTL index (auto-expire documents)
  * Multikey index (automatic on array fields)
  * list_indexes() — enumerate all indexes on a collection
  * explain() — inspect the query execution plan

RUNNING
-------
  python3 mongodb/examples/03_indexes.py

GRACEFUL DEGRADATION
--------------------
  Falls back to mongomock when no real MongoDB is available.
  Note: mongomock does NOT fully support all index features (e.g. TTL is not
  enforced, explain() output differs), but index creation calls succeed.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta
from pprint import pprint

from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, OperationFailure

CONNECTION = os.getenv("MONGODB_URI", "mongodb://localhost:27017/?replicaSet=rs0")
TIMEOUT_MS = 3000


def get_client_or_mock() -> tuple[MongoClient, bool]:
    """
    Connect to a real MongoDB server, or exit gracefully with instructions.

    Index features demonstrated here (TTL expiry, text indexes + ``$meta``
    scoring, ``explain()`` plan output) are not faithfully emulated by
    ``mongomock``, so we require a real server instead of falling back to a mock
    that would crash or mislead. The returned boolean is always ``False`` and is
    kept only for call-site compatibility.
    """
    try:
        client = MongoClient(CONNECTION, serverSelectionTimeoutMS=TIMEOUT_MS)
        client.admin.command("ping")
        print(f"Connected to real MongoDB at: {CONNECTION}")
        return client, False
    except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
        print("\n[INFO] No MongoDB server reachable — nothing to run.")
        print(f"  Reason : {exc}")
        print("\n  Start a local single-node replica set, then re-run:")
        print("    cd mongodb/ && docker compose up -d   # wait ~10s")
        print(f"  Expected URI: {CONNECTION}")
        sys.exit(0)   # configuration state, not a bug


def seed(col) -> None:
    """Insert sample messages for index demonstrations."""
    col.drop()
    col.insert_many([
        {"author": "ada",   "text": "hello from kubernetes",    "created_at": datetime(2024,1,15,10,0, tzinfo=timezone.utc), "tags": ["k8s","demo"]},
        {"author": "ada",   "text": "distributed systems rock", "created_at": datetime(2024,1,16,14,0, tzinfo=timezone.utc), "tags": ["k8s","systems"]},
        {"author": "alan",  "text": "turing test passed",       "created_at": datetime(2024,1,15,11,0, tzinfo=timezone.utc), "tags": ["ai","history"]},
        {"author": "grace", "text": "compiler bugs are features","created_at": datetime(2024,1,16, 9,0, tzinfo=timezone.utc), "tags": ["wisdom","humor"]},
        {"author": "grace", "text": "the safe ship stays in dock","created_at": datetime(2024,1,18,16,0, tzinfo=timezone.utc), "tags": ["wisdom"]},
        {"author": "linus",  "text": "linux kernel hobby project","created_at": datetime(2024,1,17, 8,0, tzinfo=timezone.utc), "tags": ["linux","kernel"]},
        {"author": "linus",  "text": "open source is powerful",   "created_at": datetime(2024,1,19,12,0, tzinfo=timezone.utc), "tags": ["linux","open-source"]},
    ])
    print(f"Seeded {col.count_documents({})} messages.")


def demo_single_field(col) -> None:
    """
    Single-Field Index
    ==================
    An index on one field; supports equality queries, range queries, and sorts
    on that field.

    ASCENDING (1) and DESCENDING (-1) are equivalent for single-field indexes
    because MongoDB can traverse the B-tree in either direction.
    """
    print("\n── Single-field index on 'author' ──")

    # create_index takes a list of (field, direction) tuples, or a string
    # shorthand for simple cases.  The name parameter gives it a human-readable
    # name; MongoDB auto-names indexes if you don't (e.g. "author_1").
    idx_name = col.create_index(
        [("author", ASCENDING)],
        name="author_asc",
        background=True  # non-blocking build (legacy option; ignored in 4.2+)
    )
    print(f"Created index: {idx_name}")

    # Query using the indexed field.
    docs = list(col.find({"author": "ada"}, {"_id": 0, "author": 1, "text": 1}))
    print(f"  find(author=ada): {len(docs)} docs found")
    for d in docs:
        print(f"    {d}")


def demo_compound(col) -> None:
    """
    Compound Index
    ==============
    An index on two or more fields.  Rules:
      * Covers queries on any LEFT PREFIX of the index key.
        Index (author, created_at) covers:
          - {author:...}                ✓ (uses the index)
          - {author:..., created_at:...} ✓
          - {created_at:...}             ✗ (no prefix match → COLLSCAN)
      * The sort order in the index matters for sorting queries.
        (author ASC, created_at DESC) is ideal for "get most recent per author."
      * A compound index can be used as a COVERED QUERY — MongoDB returns
        results from the index alone without touching the documents.
    """
    print("\n── Compound index on (author ASC, created_at DESC) ──")

    idx_name = col.create_index(
        [("author", ASCENDING), ("created_at", DESCENDING)],
        name="author_date_compound"
    )
    print(f"Created index: {idx_name}")

    # This query uses the compound index (equality on author + sort on created_at).
    docs = list(
        col.find({"author": "grace"}, {"_id": 0, "author": 1, "created_at": 1})
           .sort("created_at", DESCENDING)
    )
    print(f"  grace's messages newest-first: {len(docs)} docs")
    for d in docs:
        print(f"    {d}")


def demo_unique(col) -> None:
    """
    Unique Index
    ============
    Enforces that no two documents in the collection have the same value
    for the indexed field.  The database rejects inserts/updates that would
    violate uniqueness with a DuplicateKeyError.

    The 'unique' option is set at index creation time; you cannot add a
    unique index on a field that already has duplicate values.
    """
    print("\n── Unique index on a 'usernames' collection ──")

    # Use a separate collection to avoid interfering with messages.
    ucol = col.database.get_collection("usernames")
    ucol.drop()
    ucol.insert_many([{"username": "ada"}, {"username": "grace"}])

    idx_name = ucol.create_index(
        [("username", ASCENDING)],
        unique=True,
        name="username_unique"
    )
    print(f"Created index: {idx_name}")

    # Inserting a duplicate should fail.
    from pymongo.errors import DuplicateKeyError
    try:
        ucol.insert_one({"username": "ada"})
        print("  ERROR: Duplicate insert should have been rejected!")
    except DuplicateKeyError as e:
        print(f"  Correctly rejected duplicate 'ada': DuplicateKeyError")

    # A unique insert succeeds.
    ucol.insert_one({"username": "linus"})
    print(f"  Inserted new unique username 'linus' — OK")


def demo_text(col) -> None:
    """
    Text Index
    ==========
    Enables full-text search using the $text query operator.
    A collection can have AT MOST ONE text index, but it can cover multiple
    fields (or use {"$**": "text"} for all string fields).

    Tokenization and stemming are language-aware (default: English).
    The $meta:"textScore" projection returns the relevance score.
    """
    print("\n── Text index on 'text' field ──")

    try:
        idx_name = col.create_index(
            [("text", TEXT)],
            name="text_search",
            default_language="english"
        )
        print(f"Created index: {idx_name}")
    except OperationFailure as e:
        # A text index may already exist from a previous run — that is fine.
        print(f"  Text index already exists or minor error: {e}")

    # $text: $search is a space-separated list of terms (OR semantics by default).
    # Prefix with - to exclude a term.  Wrap in quotes for exact phrase.
    # NOTE: mongomock supports $text/$search but does NOT support the
    # {"$meta":"textScore"} sort/projection, so we catch that separately.
    try:
        results = list(col.find(
            {"$text": {"$search": "kubernetes linux"}},
            {"_id": 0, "author": 1, "text": 1, "score": {"$meta": "textScore"}}
        ).sort([("score", {"$meta": "textScore"})]))

        print(f"  $text search for 'kubernetes linux': {len(results)} results")
        for r in results:
            print(f"    score={r.get('score',0):.2f}  {r['author']}: {r['text']}")
    except (OperationFailure, TypeError) as e:
        # TypeError can happen in mongomock when $meta:"textScore" sort is used.
        # Fall back to a simple $text query without score projection.
        try:
            results = list(col.find(
                {"$text": {"$search": "kubernetes linux"}},
                {"_id": 0, "author": 1, "text": 1}
            ))
            print(f"  $text search for 'kubernetes linux': {len(results)} results (no score — mongomock)")
            for r in results:
                print(f"    {r['author']}: {r['text']}")
        except Exception as e2:
            print(f"  [NOTE] Text search unavailable in this environment: {e2}")


def demo_ttl(col) -> None:
    """
    TTL (Time-To-Live) Index
    ========================
    MongoDB automatically deletes documents once the indexed field's datetime
    value is older than expireAfterSeconds.

    The background TTL monitor runs every ~60 seconds, so documents are not
    deleted immediately — expect up to 60-second lag.

    Use cases: session tokens, rate-limit buckets, temporary job results,
    log retention.

    NOTE: mongomock does NOT enforce TTL — documents remain.
    """
    print("\n── TTL index on a 'sessions' collection ──")

    sessions = col.database.get_collection("sessions")
    sessions.drop()

    # Insert a session that "expired" 2 hours ago and one still valid.
    sessions.insert_many([
        {"token": "expired-token",  "created_at": datetime.now(timezone.utc) - timedelta(hours=2)},
        {"token": "active-token",   "created_at": datetime.now(timezone.utc)},
    ])

    # TTL index: MongoDB checks created_at; deletes docs where
    # NOW - created_at > expireAfterSeconds (here: 3600 s = 1 hour).
    idx_name = sessions.create_index(
        [("created_at", ASCENDING)],
        expireAfterSeconds=3600,   # 1 hour
        name="session_ttl"
    )
    print(f"Created TTL index: {idx_name}  (expireAfterSeconds=3600)")
    count = sessions.count_documents({})
    print(f"  Session docs now: {count}  (real MongoDB: ~60 s before TTL thread removes expired doc)")
    print("  [NOTE] mongomock enforces TTL eagerly at index-creation time,")
    print("         so the expired-token doc may already be gone here.")
    print("         Real MongoDB's TTL thread runs every ~60 s.")


def demo_multikey(col) -> None:
    """
    Multikey Index
    ==============
    When you create an index on a field that holds an ARRAY, MongoDB
    automatically creates a MULTIKEY index — one index entry per array element.

    This lets you do efficient "array contains" queries:
      find({tags: "k8s"})   ← uses the multikey index

    Limitation: a compound index cannot span two multikey fields
    (because that would explode the index size).
    """
    print("\n── Multikey index on 'tags' (array field) ──")

    # MongoDB automatically creates a multikey index when the indexed field
    # contains an array.  No special syntax needed.
    idx_name = col.create_index(
        [("tags", ASCENDING)],
        name="tags_multikey"
    )
    print(f"Created index: {idx_name}  (becomes multikey automatically)")

    # Query — "find all messages tagged 'k8s'".
    k8s_docs = list(col.find({"tags": "k8s"}, {"_id": 0, "author": 1, "tags": 1}))
    print(f"  Messages tagged 'k8s': {len(k8s_docs)}")
    for d in k8s_docs:
        print(f"    {d['author']}: {d['tags']}")

    # $all: document's array must contain ALL listed values.
    both = list(col.find({"tags": {"$all": ["linux", "kernel"]}}, {"_id": 0, "author": 1}))
    print(f"  Tagged 'linux' AND 'kernel': {[d['author'] for d in both]}")


def demo_list_indexes(col) -> None:
    """
    list_indexes() — enumerate all indexes on a collection.
    Every collection has a default index on _id (cannot be dropped).
    """
    print("\n── list_indexes() ──")
    for idx in col.list_indexes():
        key_str = str(dict(idx["key"]))
        unique   = " UNIQUE" if idx.get("unique") else ""
        sparse   = " SPARSE" if idx.get("sparse") else ""
        ttl      = f" TTL:{idx['expireAfterSeconds']}s" if "expireAfterSeconds" in idx else ""
        print(f"  [{idx['name']}] key={key_str}{unique}{sparse}{ttl}")


def demo_explain(col, is_mock: bool) -> None:
    """
    explain() — show the query execution plan.
    ==========================================
    explain("executionStats") returns detailed information about how MongoDB
    executed the query, including:

      winningPlan.inputStage.stage:
        "IXSCAN"   — used an index   (fast for large collections)
        "COLLSCAN" — full scan       (slow; add an index!)
        "FETCH"    — loaded docs from storage after an index scan

      executionStats.nReturned         — how many docs were returned
      executionStats.totalDocsExamined — how many docs were read from storage
      executionStats.totalKeysExamined — how many index entries were scanned

    A well-indexed query has nReturned ≈ totalDocsExamined ≈ totalKeysExamined.
    A poor query has totalDocsExamined >> nReturned.
    """
    print("\n── explain() — query plan inspection ──")

    if is_mock:
        print("  [NOTE] mongomock returns a simplified explain() output.")
        print("         Use a real MongoDB instance to see full execution stats.")

    query = {"author": "ada"}

    try:
        # pymongo Cursor.explain() — note: mongomock's Cursor does not
        # implement explain(); we catch AttributeError below.
        cursor = col.find(query)
        if not hasattr(cursor, "explain"):
            raise AttributeError("mongomock cursor does not support explain()")
        plan = cursor.explain()

        # Navigate the plan — real MongoDB has a nested structure;
        # mongomock may return a flatter structure.
        query_planner = plan.get("queryPlanner", {})
        winning_plan  = query_planner.get("winningPlan", {})
        input_stage   = winning_plan.get("inputStage", {})
        stage         = input_stage.get("stage", winning_plan.get("stage", "UNKNOWN"))
        index_name    = input_stage.get("indexName", "N/A")

        exec_stats    = plan.get("executionStats", {})
        n_returned    = exec_stats.get("nReturned", "N/A")
        docs_examined = exec_stats.get("totalDocsExamined", "N/A")
        keys_examined = exec_stats.get("totalKeysExamined", "N/A")

        print(f"  Query: {query}")
        print(f"  Stage:         {stage}")
        print(f"  Index used:    {index_name}")
        print(f"  nReturned:     {n_returned}")
        print(f"  docsExamined:  {docs_examined}")
        print(f"  keysExamined:  {keys_examined}")

        if stage == "IXSCAN":
            print("  → Index scan (efficient)")
        elif stage == "COLLSCAN":
            print("  → Collection scan (no index; consider adding one)")
        else:
            print(f"  → Plan stage: {stage}")

    except AttributeError:
        # mongomock's cursor lacks explain() — just describe what it would show.
        print(f"  Query: {query}")
        print("  explain() not available in mongomock.")
        print("  On a real MongoDB instance, look for:")
        print("    winningPlan.inputStage.stage = 'IXSCAN'  → index used (good)")
        print("    winningPlan.inputStage.stage = 'COLLSCAN' → full scan (add an index)")
        print("  Command: db.messages.find({author:'ada'}).explain('executionStats')")
    except Exception as e:
        print(f"  explain() error: {e}")


def main() -> None:
    print("=" * 60)
    print(" 03_indexes.py — MongoDB Index Types + explain()")
    print(f" URI: {CONNECTION}")
    print("=" * 60)

    client, is_mock = get_client_or_mock()
    db  = client["guestbook_index_demo"]
    col = db["messages"]

    try:
        seed(col)
        demo_single_field(col)
        demo_compound(col)
        demo_unique(col)
        demo_text(col)
        demo_ttl(col)
        demo_multikey(col)
        demo_list_indexes(col)
        demo_explain(col, is_mock)
    finally:
        client.close()

    print("\n✓ 03_indexes.py complete.")


if __name__ == "__main__":
    main()
