"""
05_change_streams.py — Real-Time Change Streams with PyMongo
============================================================

Covers:
  * Opening a watch() change stream on a collection
  * Filtering event types ($match on operationType)
  * Resuming a stream after disconnection (resume_after token)
  * Timeout-based reading (max_await_time_ms)
  * Triggering events from a second shell

WHY CHANGE STREAMS NEED A REPLICA SET
---------------------------------------
Change streams are implemented on top of the OPLOG — the special capped
collection (`local.oplog.rs`) that the primary uses to record every write
in a replication-ready format.

Without --replSet / rs.initiate(), there is no oplog, and MongoDB raises:
  pymongo.errors.OperationFailure: The $changeStream stage is only supported
  on replica sets

This means: even a single-node mongod must be started with --replSet and
initiated via rs.initiate() before change streams work.

HOW TO TRIGGER EVENTS FROM ANOTHER SHELL
------------------------------------------
While this script is running (listening mode), open a second terminal:

  docker compose exec mongo mongosh guestbook
  db.messages.insertOne({author:"test", text:"ping", created_at:new Date()})
  db.messages.updateOne({author:"test"}, {$set:{text:"pong"}})
  db.messages.deleteOne({author:"test"})

You should see the events printed by this script.

RUNNING
-------
  cd mongodb/ && docker compose up -d   # start replica set first
  python3 mongodb/examples/05_change_streams.py

  # Custom URI:
  MONGODB_URI="mongodb://host:27017/?replicaSet=rs0" python3 05_change_streams.py

GRACEFUL DEGRADATION
--------------------
  If no server is reachable, or the server does not support change streams
  (standalone), the script prints instructions and exits cleanly.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone

from pymongo import MongoClient
from pymongo.errors import (
    ConnectionFailure,
    ServerSelectionTimeoutError,
    OperationFailure,
    PyMongoError,
)

CONNECTION    = os.getenv("MONGODB_URI", "mongodb://localhost:27017/?replicaSet=rs0")
TIMEOUT_MS    = 4000
# How long to wait for each event before giving up (milliseconds).
# Keeping this short prevents the script from hanging in automated/demo contexts.
STREAM_TIMEOUT_MS = 3000
# Maximum number of events to collect before exiting.
MAX_EVENTS    = 5
# Maximum total seconds to spend watching.
WATCH_TIMEOUT_S = 15


def get_client() -> MongoClient:
    client = MongoClient(CONNECTION, serverSelectionTimeoutMS=TIMEOUT_MS)
    client.admin.command("ping")
    return client


def explain_change_stream_event(event: dict) -> str:
    """
    Format a change stream event for human-readable display.

    Event document fields:
      operationType : "insert" | "update" | "replace" | "delete" | "drop" | "rename" | "invalidate"
      documentKey   : { _id: <id> } — which document changed
      fullDocument  : the full document AFTER the change (inserts, replaces;
                      for updates, only with { fullDocument: "updateLookup" })
      updateDescription : { updatedFields: {...}, removedFields: [...] }  (updates only)
      ns            : { db: "...", coll: "..." }
      clusterTime   : Timestamp (oplog clock; use for resume_after)
      _id           : the RESUME TOKEN — save this to resume after disconnection
    """
    op   = event.get("operationType", "?")
    key  = event.get("documentKey", {})
    ns   = event.get("ns", {})

    parts = [f"op={op}", f"key={key}", f"ns={ns.get('db')}.{ns.get('coll')}"]

    if op == "insert":
        doc = event.get("fullDocument", {})
        parts.append(f"author={doc.get('author','?')} text={str(doc.get('text','?'))[:40]}")
    elif op == "update":
        upd = event.get("updateDescription", {})
        parts.append(f"updatedFields={upd.get('updatedFields')}")
    elif op == "delete":
        parts.append("(document deleted)")

    return "  " + "  |  ".join(parts)


def demo_watch(client: MongoClient) -> None:
    """
    Open a change stream on messages, collect up to MAX_EVENTS events,
    then exit.  Uses a short getMore timeout so the loop doesn't block.
    """
    db  = client["guestbook"]
    col = db["messages"]

    # Seed a few messages so the collection definitely exists
    # (change streams can only be opened on existing collections).
    col.update_one(
        {"_init": True},
        {"$setOnInsert": {"_init": True, "created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )

    # ── Build the pipeline filter ────────────────────────────────────────────
    # The pipeline passed to watch() uses aggregation operators, just like
    # collection.aggregate(), but only a limited set of stages is allowed
    # ($match, $project, $addFields, $replaceRoot, $redact).
    pipeline = [
        {"$match": {
            "operationType": {"$in": ["insert", "update", "replace", "delete"]}
        }}
    ]

    print("\nOpening change stream on guestbook.messages...")
    print(f"Listening for up to {MAX_EVENTS} events or {WATCH_TIMEOUT_S}s (whichever comes first).")
    print()
    print("To trigger events, open a second terminal and run:")
    print("  docker compose exec mongo mongosh guestbook")
    print("  db.messages.insertOne({author:'test', text:'ping', created_at:new Date()})")
    print("  db.messages.updateOne({author:'test'},{$set:{text:'updated!'}})")
    print("  db.messages.deleteOne({author:'test'})")
    print()

    resume_token = None    # save the last token to resume after a disconnect
    events_seen  = 0
    start_time   = time.time()

    try:
        # watch() opens a special aggregation cursor backed by the oplog.
        # max_await_time_ms: how long each getMore waits for new events
        #   before returning an empty batch (avoids infinite blocking).
        # full_document="updateLookup": for update events, MongoDB does an
        #   extra read to return the current full document (post-update).
        with col.watch(
            pipeline,
            max_await_time_ms=STREAM_TIMEOUT_MS,
            full_document="updateLookup",
            resume_after=resume_token,   # None on first open
        ) as stream:
            # We use try_next() in a bounded loop rather than `for event in
            # stream:`. The blocking iterator never returns control when no
            # events arrive (it just keeps polling), so the timeout below would
            # never fire. try_next() returns None after max_await_time_ms with
            # no event, letting us check the deadline and exit cleanly -- which
            # is what makes this script self-terminating in automated runs.
            while True:
                event = stream.try_next()
                resume_token = stream.resume_token  # save for potential resume

                if event is None:
                    # No event this interval. Stop once we hit the time budget.
                    if time.time() - start_time > WATCH_TIMEOUT_S:
                        print(f"Reached watch timeout ({WATCH_TIMEOUT_S}s) — closing stream.")
                        break
                    continue

                events_seen += 1
                ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                print(f"[{ts}] Event #{events_seen}:")
                print(explain_change_stream_event(event))
                print()

                if events_seen >= MAX_EVENTS:
                    print(f"Reached MAX_EVENTS ({MAX_EVENTS}) — closing stream.")
                    break

    except KeyboardInterrupt:
        print("\nInterrupted by user.")

    elapsed = time.time() - start_time
    print(f"\nChange stream closed.  Collected {events_seen} events in {elapsed:.1f}s.")

    if events_seen == 0:
        print("\n[NOTE] No events received within the timeout.")
        print("  This is expected in automated environments where no other")
        print("  client is writing to the collection.")
        print("  Run the script and then INSERT docs from another shell to see events.")

    if resume_token:
        print(f"\nResume token saved: {resume_token}")
        print("  You can pass this to col.watch(..., resume_after=token) to")
        print("  resume the stream from where it left off after a reconnect.")


# =============================================================================
# MAIN
# =============================================================================
def main() -> None:
    print("=" * 60)
    print(" 05_change_streams.py — Real-Time Change Streams")
    print(f" URI: {CONNECTION}")
    print("=" * 60)

    # ── Connect ──────────────────────────────────────────────────────────────
    try:
        client = get_client()
        print(f"Connected.  Server version: {client.server_info()['version']}")
    except (ConnectionFailure, ServerSelectionTimeoutError) as exc:
        print("\n[ERROR] Cannot connect to MongoDB.")
        print(f"  Reason: {exc}")
        print()
        print("  Change streams require a running replica set.")
        print("  Start one with Docker Compose:")
        print()
        print("    cd mongodb/")
        print("    docker compose up -d")
        print("    # wait ~10 seconds, then:")
        print("    python3 mongodb/examples/05_change_streams.py")
        sys.exit(0)

    try:
        demo_watch(client)

    except OperationFailure as exc:
        # Code 40573: $changeStream stage requires a replica set
        if exc.code in (40573, 136):
            print("\n[ERROR] Change streams are not supported on this server.")
            print("  This usually means MongoDB was started WITHOUT --replSet.")
            print()
            print("  Make sure you are connecting to the Docker Compose replica set:")
            print("    cd mongodb/ && docker compose up -d")
            print("  URI used:", CONNECTION)
        else:
            print(f"\n[ERROR] MongoDB operation error (code {exc.code}): {exc}")
        sys.exit(0)
    except PyMongoError as exc:
        print(f"\n[ERROR] Unexpected MongoDB error: {exc}")
        sys.exit(1)
    finally:
        client.close()

    print("\n✓ 05_change_streams.py complete.")


if __name__ == "__main__":
    main()
