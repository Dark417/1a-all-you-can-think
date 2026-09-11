"""
01_crud.py — MongoDB CRUD Operations with PyMongo
==================================================

Covers:
  * insert_one / insert_many
  * find with query operators ($gt, $in, $regex, $exists) and projection
  * update_one / update_many with $set, $inc, $push
  * replace_one
  * delete_one / delete_many
  * count_documents / estimated_document_count

RUNNING
-------
  # With the Docker Compose replica set running:
  python3 mongodb/examples/01_crud.py

  # Custom server:
  MONGODB_URI="mongodb://host:27017/?replicaSet=rs0" python3 01_crud.py

GRACEFUL DEGRADATION
--------------------
  If no MongoDB server is reachable, the script catches the connection error,
  prints clear instructions, and exits with code 0 — no traceback.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta
from pprint import pprint

# ---------------------------------------------------------------------------
# pymongo — the official Python driver for MongoDB.
# MongoClient is the connection pool; it is thread-safe and should be shared.
# ---------------------------------------------------------------------------
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError, PyMongoError

# ---------------------------------------------------------------------------
# Connection string from environment variable (12-factor).
# Default points to the Docker Compose single-node replica set.
# ---------------------------------------------------------------------------
CONNECTION = os.getenv("MONGODB_URI", "mongodb://localhost:27017/?replicaSet=rs0")
# Short timeout so the script fails fast when no server is up.
TIMEOUT_MS = 3000


def get_client() -> MongoClient:
    """Create and verify a MongoClient.  Raises ConnectionFailure on error."""
    client = MongoClient(CONNECTION, serverSelectionTimeoutMS=TIMEOUT_MS)
    # force_connect: actually try to connect (MongoClient is lazy by default).
    client.admin.command("ping")
    return client


def demo_insert(col) -> list:
    """
    insert_one / insert_many
    ========================
    insert_one  : insert a single document; returns InsertOneResult with
                  .inserted_id — the value stored in _id (auto-generated ObjectId
                  if you don't supply one).
    insert_many : insert a list of documents in one network round-trip; returns
                  InsertManyResult with .inserted_ids list.
    """
    print("\n── INSERT ──")

    # Clean up from previous runs so the script is idempotent.
    col.delete_many({"_example": "crud"})

    # insert_one — the driver sets doc["_id"] in-place after insert.
    doc = {
        "_example": "crud",
        "author":   "ada",
        "text":     "hello from kubernetes",
        "created_at": datetime.now(timezone.utc),
        "tags":     ["k8s", "demo"],
        "view_count": 0,
    }
    result = col.insert_one(doc)
    # result.inserted_id is the ObjectId (or the value you supplied as _id).
    print(f"insert_one  → _id = {result.inserted_id}")

    # insert_many — batch is faster than N individual inserts.
    docs = [
        {"_example": "crud", "author": "alan",  "text": "turing was here",     "created_at": datetime.now(timezone.utc) - timedelta(hours=2), "tags": ["history"], "view_count": 5},
        {"_example": "crud", "author": "grace", "text": "bugs are a feature",  "created_at": datetime.now(timezone.utc) - timedelta(hours=1), "tags": ["wisdom"],  "view_count": 12},
        {"_example": "crud", "author": "ada",   "text": "another ada message", "created_at": datetime.now(timezone.utc) - timedelta(minutes=30), "tags": ["demo"],  "view_count": 3},
        {"_example": "crud", "author": "linus",  "text": "just a hobby",       "created_at": datetime.now(timezone.utc) - timedelta(minutes=10), "tags": ["demo"],  "view_count": 7},
    ]
    result_many = col.insert_many(docs)
    print(f"insert_many → {len(result_many.inserted_ids)} docs inserted")

    return result_many.inserted_ids


def demo_find(col) -> None:
    """
    find / find_one — READ operations
    ==================================
    find(filter, projection)
      filter     : dict of query conditions (same syntax as mongosh).
      projection : dict controlling which fields to return.
                   { field: 1 } = include,  { field: 0 } = exclude.
                   Cannot mix inclusions and exclusions (except _id).

    Cursors are lazy — documents are fetched from the server only when
    you iterate.  Use .limit() / .skip() / .sort() on the cursor object.
    """
    print("\n── FIND ──")

    # --- Simple equality filter ---
    print("\nMessages by 'ada':")
    for doc in col.find({"author": "ada", "_example": "crud"}):
        print(f"  {doc['author']}: {doc['text']}")

    # --- Query operators ---
    # $gt / $lte: comparison operators.
    print("\nDocs with view_count > 4:")
    for doc in col.find({"_example": "crud", "view_count": {"$gt": 4}}, {"author": 1, "view_count": 1, "_id": 0}):
        print(f"  {doc['author']}: {doc['view_count']} views")

    # $in: field value is one of a list.
    print("\nAuthors in [ada, grace]:")
    for doc in col.find({"_example": "crud", "author": {"$in": ["ada", "grace"]}}, {"author": 1, "text": 1, "_id": 0}):
        print(f"  {doc['author']}: {doc['text']}")

    # $regex: regular expression match.
    print("\nText matching /turing|bugs/ (regex):")
    for doc in col.find({"_example": "crud", "text": {"$regex": "turing|bugs", "$options": "i"}}, {"author": 1, "text": 1, "_id": 0}):
        print(f"  {doc['author']}: {doc['text']}")

    # $exists: field is present (or absent).
    print("\nDocs where 'tags' field exists:")
    count = col.count_documents({"_example": "crud", "tags": {"$exists": True}})
    print(f"  {count} docs have a 'tags' field")

    # --- Projection ---
    # 1 = include the field, 0 = exclude.  _id is included by default.
    print("\nProjection — author & text only (no _id):")
    for doc in col.find({"_example": "crud"}, {"author": 1, "text": 1, "_id": 0}).limit(3):
        pprint(doc)

    # --- Sort + limit ---
    print("\nNewest 3 messages (sort by created_at descending):")
    for doc in col.find({"_example": "crud"}).sort("created_at", DESCENDING).limit(3):
        ts = doc["created_at"].strftime("%H:%M:%S") if isinstance(doc.get("created_at"), datetime) else "?"
        print(f"  [{ts}] {doc['author']}: {doc['text']}")

    # --- find_one ---
    # Returns the first matching document (or None).
    one = col.find_one({"_example": "crud", "author": "grace"})
    print(f"\nfind_one(grace) text: {one['text'] if one else 'NOT FOUND'}")

    # --- count_documents ---
    # Accurate count that respects the filter; uses index if available.
    total = col.count_documents({"_example": "crud"})
    print(f"\ncount_documents total: {total}")


def demo_update(col) -> None:
    """
    update_one / update_many / replace_one
    =======================================
    Update operators (used inside the update document):
      $set   : set specific field(s)
      $unset : remove field(s)
      $inc   : atomically add/subtract a number
      $push  : append a value to an array field
      $pull  : remove values matching a condition from an array
      $addToSet : append to array only if value is not already present

    upsert=True : insert a new document if no document matches the filter.
    """
    print("\n── UPDATE ──")

    # $set — update specific fields without touching others.
    result = col.update_one(
        {"_example": "crud", "author": "ada", "text": "hello from kubernetes"},
        {"$set": {"text": "hello from kubernetes (updated)", "edited": True}}
    )
    print(f"update_one ($set): matched={result.matched_count}, modified={result.modified_count}")

    # $inc + $push — atomically increment a counter AND append to an array.
    result = col.update_one(
        {"_example": "crud", "author": "grace"},
        {
            "$inc":  {"view_count": 1},       # increment; creates field if missing
            "$push": {"tags": "inspirational"} # append to array
        }
    )
    doc = col.find_one({"_example": "crud", "author": "grace"})
    print(f"update_one ($inc+$push): grace now has {doc.get('view_count')} views, tags={doc.get('tags')}")

    # update_many — apply the same update to all matching documents.
    result_many = col.update_many(
        {"_example": "crud", "view_count": {"$lt": 5}},
        {"$set": {"low_traffic": True}}
    )
    print(f"update_many (low_traffic): modified {result_many.modified_count} docs")

    # upsert — insert if not found, update if found.
    result_upsert = col.update_one(
        {"_example": "crud", "author": "django"},
        {"$setOnInsert": {"_example": "crud", "author": "django", "text": "upserted doc", "created_at": datetime.now(timezone.utc)}},
        upsert=True
    )
    print(f"upsert: upserted_id={result_upsert.upserted_id}")

    # replace_one — replace the ENTIRE document (except _id).
    # Use carefully: it wipes all fields not in the replacement.
    col.replace_one(
        {"_example": "crud", "author": "django"},
        {"_example": "crud", "author": "django", "text": "replaced entirely", "created_at": datetime.now(timezone.utc)}
    )
    replaced = col.find_one({"_example": "crud", "author": "django"})
    print(f"replace_one: {replaced}")


def demo_delete(col) -> None:
    """
    delete_one / delete_many
    ========================
    delete_one  : remove the first document matching the filter.
    delete_many : remove ALL documents matching the filter.

    Both return a DeleteResult with .deleted_count.
    """
    print("\n── DELETE ──")

    # delete_one — remove a single document.
    result = col.delete_one({"_example": "crud", "author": "django"})
    print(f"delete_one (django): deleted {result.deleted_count}")

    # delete_many — clean up all example docs.
    result_many = col.delete_many({"_example": "crud"})
    print(f"delete_many (_example=crud): deleted {result_many.deleted_count}")

    remaining = col.count_documents({"_example": "crud"})
    print(f"Remaining example docs: {remaining}  (should be 0)")


def main() -> None:
    print("=" * 60)
    print(" 01_crud.py — MongoDB CRUD with PyMongo")
    print(f" URI: {CONNECTION}")
    print("=" * 60)

    # ── Connect ──────────────────────────────────────────────────────────────
    # We catch both ConnectionFailure and ServerSelectionTimeoutError.
    # ServerSelectionTimeoutError is a subclass of ConnectionFailure but
    # is more specific: it means pymongo exhausted its server-selection
    # timeout without finding a suitable server (no server reachable at all).
    try:
        client = get_client()
    except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
        print("\n[ERROR] Cannot connect to MongoDB.")
        print(f"  Reason : {exc}")
        print()
        print("  To start a local single-node replica set, run:")
        print("    cd mongodb/")
        print("    docker compose up -d")
        print("  Then wait ~10 seconds and re-run this script.")
        print()
        print("  Expected URI:", CONNECTION)
        sys.exit(0)   # exit 0 — this is a configuration issue, not a bug

    print(f"Connected to MongoDB.  Server info: {client.server_info()['version']}")

    db = client["guestbook_crud_demo"]
    col = db["messages"]

    try:
        demo_insert(col)
        demo_find(col)
        demo_update(col)
        demo_delete(col)
    except PyMongoError as exc:
        print(f"\n[ERROR] MongoDB operation failed: {exc}")
        sys.exit(1)
    finally:
        # Always close the client so background threads are shut down cleanly.
        client.close()

    print("\n✓ 01_crud.py complete.")


if __name__ == "__main__":
    main()
