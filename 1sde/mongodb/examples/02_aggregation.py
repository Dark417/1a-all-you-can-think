"""
02_aggregation.py — MongoDB Aggregation Pipeline with PyMongo
=============================================================

Covers:
  * $match — filter documents (same as find() query)
  * $group — group and compute accumulators ($sum, $avg, $max, $push, $addToSet)
  * $sort  — order results
  * $project — reshape documents, add computed fields
  * $lookup — left-outer join with another collection
  * $unwind — deconstruct array fields
  * $facet  — run multiple sub-pipelines in parallel
  * $bucket — group into value ranges
  * $addFields — add fields without removing others

RUNNING
-------
  python3 mongodb/examples/02_aggregation.py
  MONGODB_URI="mongodb://host:27017/?replicaSet=rs0" python3 02_aggregation.py

GRACEFUL DEGRADATION
--------------------
  Falls back to mongomock when no real MongoDB server is reachable, so the
  pipeline examples still execute and produce output.  Some mongomock
  limitations (e.g. complex $lookup pipelines) are noted inline.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta
from pprint import pprint

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

# ---------------------------------------------------------------------------
# Connection — environment variable with a sensible default.
# ---------------------------------------------------------------------------
CONNECTION = os.getenv("MONGODB_URI", "mongodb://localhost:27017/?replicaSet=rs0")
TIMEOUT_MS = 3000

# ---------------------------------------------------------------------------
# Seed data shared across all aggregation demos.
# ---------------------------------------------------------------------------
MESSAGES = [
    {"author": "ada",   "text": "hello from kubernetes",    "created_at": datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),  "tags": ["k8s", "demo"],    "word_count": 3},
    {"author": "ada",   "text": "another message from ada", "created_at": datetime(2024, 1, 16, 14, 0, tzinfo=timezone.utc),  "tags": ["demo"],            "word_count": 4},
    {"author": "alan",  "text": "turing was here",          "created_at": datetime(2024, 1, 15, 11, 30, tzinfo=timezone.utc), "tags": ["history"],         "word_count": 3},
    {"author": "grace", "text": "bugs are a feature",       "created_at": datetime(2024, 1, 16, 9, 0, tzinfo=timezone.utc),   "tags": ["wisdom", "humor"], "word_count": 4},
    {"author": "grace", "text": "the only safe ship is one in dry dock", "created_at": datetime(2024, 1, 18, 16, 0, tzinfo=timezone.utc), "tags": ["wisdom"], "word_count": 10},
    {"author": "linus",  "text": "just a hobby project",    "created_at": datetime(2024, 1, 17, 8, 0, tzinfo=timezone.utc),   "tags": ["k8s", "humor"],    "word_count": 4},
]

ORDERS = [
    {"order_id": "O-001", "customer": "ada",   "product": "K8s Book",  "amount": 49.99, "status": "shipped"},
    {"order_id": "O-002", "customer": "ada",   "product": "Mongo Book", "amount": 39.99, "status": "pending"},
    {"order_id": "O-003", "customer": "alan",  "product": "K8s Book",  "amount": 49.99, "status": "shipped"},
    {"order_id": "O-004", "customer": "grace", "product": "Python Book","amount": 29.99, "status": "shipped"},
    {"order_id": "O-005", "customer": "grace", "product": "Mongo Book", "amount": 39.99, "status": "cancelled"},
    {"order_id": "O-006", "customer": "linus",  "product": "Linux Book", "amount": 34.99, "status": "shipped"},
]

USERS = [
    {"username": "ada",   "email": "ada@example.com",   "role": "admin"},
    {"username": "alan",  "email": "alan@example.com",  "role": "user"},
    {"username": "grace", "email": "grace@example.com", "role": "user"},
]


def get_client_or_mock() -> tuple[MongoClient, bool]:
    """
    Connect to a real MongoDB server, or exit gracefully with instructions.

    Earlier revisions fell back to an in-memory ``mongomock``, but the
    aggregation operators showcased here (``$round``, ``$lookup``, ``$facet`` …)
    are exactly the features mongomock does not faithfully implement -- running
    them on the mock would crash or mislead. So we require a real server (the
    provided docker-compose brings one up in seconds) and degrade cleanly when
    none is reachable. The boolean in the return tuple is kept for call-site
    compatibility and is always ``False`` (never a mock).
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


def seed(db, is_mock: bool) -> None:
    """Insert demo data, wiping previous runs first."""
    db.messages.drop()
    db.orders.drop()
    db.users.drop()
    db.messages.insert_many(MESSAGES)
    db.orders.insert_many(ORDERS)
    db.users.insert_many(USERS)
    print(f"Seeded {db.messages.count_documents({})} messages, "
          f"{db.orders.count_documents({})} orders, "
          f"{db.users.count_documents({})} users.")


# =============================================================================
# DEMO 1 — $match + $group + $sort + $project
# =============================================================================
def demo_match_group_sort_project(db) -> None:
    """
    Classic analytics query: count messages per author, most active first.

    Pipeline stages:
      $match   — pre-filter to only process relevant docs (always put $match
                 FIRST to reduce data flowing through later stages).
      $group   — group docs by a key expression; accumulators compute values
                 across the group.
      $sort    — order the grouped results.
      $project — rename/reshape the output document.
    """
    print("\n── DEMO 1: $match + $group + $sort + $project ──")
    print("  Message count per author, most active first:")

    pipeline = [
        # Stage 1: only include docs that have an 'author' field.
        # A real app might also filter by date range here, e.g.:
        #   { "created_at": { "$gte": datetime(2024,1,1) } }
        {"$match": {"author": {"$exists": True}}},

        # Stage 2: group by author.
        # _id         : the group key — "$author" means the value of the author field.
        # count       : $sum:1 increments a counter for each document in the group.
        # total_words : $sum:"$word_count" sums a numeric field across the group.
        # last_msg    : $max:"$created_at" — the latest timestamp in the group.
        # all_tags    : $push:"$tags" — collect ALL tags arrays into a nested array.
        {"$group": {
            "_id":         "$author",
            "count":       {"$sum": 1},
            "total_words": {"$sum": "$word_count"},
            "last_msg":    {"$max": "$created_at"},
            "all_tags":    {"$push": "$tags"},     # results in array of arrays
        }},

        # Stage 3: sort by count descending, then by author alphabetically.
        {"$sort": {"count": -1, "_id": 1}},

        # Stage 4: reshape the output.
        # _id:0 hides the group key field; we rename it to "author".
        # avg_words = total_words / count  (Python will round when printing).
        # NOTE: $round is not supported by mongomock, so we use $divide here
        # and round the Python float when printing.
        {"$project": {
            "_id":    0,
            "author": "$_id",          # rename _id → author
            "count":  1,
            "avg_words": {"$divide": ["$total_words", "$count"]},
            "last_msg": 1,
        }},
    ]

    for doc in db.messages.aggregate(pipeline):
        print(f"  {doc['author']:10} {doc['count']} msgs, "
              f"avg {doc['avg_words']:.1f} words/msg")


# =============================================================================
# DEMO 2 — $unwind + $group (flatten arrays)
# =============================================================================
def demo_unwind(db) -> None:
    """
    $unwind: deconstruct an array field.
    Each element of the array becomes a SEPARATE document in the pipeline.

    Use case: analyse individual array elements (tags, line items, etc.)
    rather than treating the whole array as one value.
    """
    print("\n── DEMO 2: $unwind — tag frequency ──")

    pipeline = [
        # Every message has a 'tags' array, e.g. ["k8s", "demo"].
        {"$match": {"tags": {"$exists": True}}},

        # $unwind emits one doc per array element.
        # { author:"ada", tags:["k8s","demo"] }
        #   →  { author:"ada", tags:"k8s" }
        #   →  { author:"ada", tags:"demo" }
        {"$unwind": "$tags"},

        # Now we can group on individual tag values.
        {"$group": {
            "_id":    "$tags",
            "count":  {"$sum": 1},
            "authors": {"$addToSet": "$author"}  # unique authors per tag
        }},

        {"$sort":    {"count": -1}},
        {"$project": {"_id": 0, "tag": "$_id", "count": 1, "authors": 1}},
    ]

    print("  Tag usage across all messages:")
    for doc in db.messages.aggregate(pipeline):
        print(f"  #{doc['tag']:12} {doc['count']}x — authors: {sorted(doc['authors'])}")


# =============================================================================
# DEMO 3 — $lookup (join with another collection)
# =============================================================================
def demo_lookup(db, is_mock: bool) -> None:
    """
    $lookup: left-outer join.
    Adds a new array field to each document containing the matching docs
    from the foreign collection.

    Equivalent SQL: SELECT m.*, u.email FROM messages m
                    LEFT JOIN users u ON m.author = u.username
    """
    print("\n── DEMO 3: $lookup — join messages with users ──")
    if is_mock:
        print("  [NOTE] mongomock has limited $lookup support — showing basic form.")

    pipeline = [
        # Stage 1: join messages (local) → users (foreign).
        # 'as' names the new array field on each message document.
        {"$lookup": {
            "from":         "users",    # the other collection
            "localField":   "author",   # field in messages
            "foreignField": "username", # field in users
            "as":           "user_info" # output array field
        }},

        # Stage 2: only keep messages where a matching user was found.
        {"$match": {"user_info": {"$ne": []}}},

        # Stage 3: $unwind the user_info array (0 or 1 element since username is unique).
        # preserveNullAndEmptyArrays:true keeps docs with no match (LEFT JOIN semantics).
        {"$unwind": {"path": "$user_info", "preserveNullAndEmptyArrays": True}},

        # Stage 4: project only interesting fields.
        {"$project": {
            "_id":   0,
            "author": 1,
            "text":  {"$substr": ["$text", 0, 35]},  # truncate long texts
            "role":  "$user_info.role",
            "email": "$user_info.email",
        }},
        {"$limit": 5},
    ]

    for doc in db.messages.aggregate(pipeline):
        print(f"  [{doc.get('role','?'):5}] {doc.get('author'):8} ({doc.get('email','?')}) : {doc.get('text')}")


# =============================================================================
# DEMO 4 — $facet (multi-dimensional analytics in one round trip)
# =============================================================================
def demo_facet(db) -> None:
    """
    $facet: run multiple sub-pipelines on the SAME input documents in one
    aggregation call.  Returns a single document with one key per sub-pipeline.

    This avoids multiple round trips when you need, e.g., totals + top-N +
    histogram at the same time.
    """
    print("\n── DEMO 4: $facet — combined stats in one query ──")

    pipeline = [
        # Optional pre-filter before feeding into all facets.
        {"$match": {"author": {"$exists": True}}},

        {"$facet": {
            # Sub-pipeline A: total count.
            "total": [
                {"$count": "n"}
            ],

            # Sub-pipeline B: top 3 authors by message count.
            "top_authors": [
                {"$group": {"_id": "$author", "n": {"$sum": 1}}},
                {"$sort":  {"n": -1}},
                {"$limit": 3},
                {"$project": {"_id": 0, "author": "$_id", "msgs": "$n"}},
            ],

            # Sub-pipeline C: 3 most recent messages.
            "recent": [
                {"$sort":    {"created_at": -1}},
                {"$limit":   3},
                {"$project": {"_id": 0, "author": 1, "text": {"$substr": ["$text", 0, 40]}}},
            ],

            # Sub-pipeline D: word count distribution using $bucket.
            # $bucket splits documents into ranges defined by 'boundaries'.
            "word_count_dist": [
                {"$bucket": {
                    "groupBy":    "$word_count",
                    "boundaries": [0, 4, 7, 15],   # ranges: [0,4), [4,7), [7,15)
                    "default":    "other",           # docs not matching any range
                    "output":     {"count": {"$sum": 1}},
                }},
            ],
        }},
    ]

    result = next(db.messages.aggregate(pipeline))

    total = result["total"][0]["n"] if result["total"] else 0
    print(f"\n  Total messages: {total}")

    print("  Top authors:")
    for a in result["top_authors"]:
        print(f"    {a['author']}: {a['msgs']} messages")

    print("  Most recent:")
    for r in result["recent"]:
        print(f"    {r['author']}: {r['text']}")

    print("  Word count distribution:")
    for bucket in result.get("word_count_dist", []):
        label = f"{bucket['_id']}"
        print(f"    {label}: {bucket['count']} messages")


# =============================================================================
# DEMO 5 — Order analytics pipeline ($match + $group + $sort + $lookup)
# =============================================================================
def demo_orders(db, is_mock: bool) -> None:
    """
    A more realistic "orders analytics" pipeline combining multiple stages.
    Shows revenue per customer with their email address from the users collection.
    """
    print("\n── DEMO 5: Order analytics with $lookup ──")

    pipeline = [
        # Only count shipped orders (ignore pending/cancelled).
        {"$match": {"status": "shipped"}},

        # Revenue and order count per customer.
        {"$group": {
            "_id":          "$customer",
            "total_revenue":{"$sum": "$amount"},
            "order_count":  {"$sum": 1},
            "products":     {"$addToSet": "$product"},
        }},

        # Sort by revenue descending.
        {"$sort": {"total_revenue": -1}},

        # Join with users to get email.
        {"$lookup": {
            "from":         "users",
            "localField":   "_id",
            "foreignField": "username",
            "as":           "user",
        }},
        {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": True}},

        # Final shape.
        {"$project": {
            "_id":           0,
            "customer":      "$_id",
            "email":         {"$ifNull": ["$user.email", "unknown"]},
            "total_revenue": "$total_revenue",   # round in Python (mongomock lacks $round)
            "order_count":   1,
            "products":      1,
        }},
    ]

    print("  Shipped-order revenue per customer:")
    for doc in db.orders.aggregate(pipeline):
        revenue = round(doc['total_revenue'], 2)
        print(f"  {doc['customer']:8} ({doc['email']:<20}) "
              f"${revenue:6.2f} over {doc['order_count']} orders")


# =============================================================================
# MAIN
# =============================================================================
def main() -> None:
    print("=" * 60)
    print(" 02_aggregation.py — MongoDB Aggregation Pipeline")
    print(f" URI: {CONNECTION}")
    print("=" * 60)

    client, is_mock = get_client_or_mock()
    db = client["guestbook_agg_demo"]
    seed(db, is_mock)

    try:
        demo_match_group_sort_project(db)
        demo_unwind(db)
        demo_lookup(db, is_mock)
        demo_facet(db)
        demo_orders(db, is_mock)
    finally:
        client.close()

    print("\n✓ 02_aggregation.py complete.")


if __name__ == "__main__":
    main()
