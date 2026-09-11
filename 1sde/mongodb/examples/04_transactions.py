"""
04_transactions.py — Multi-Document ACID Transactions with PyMongo
==================================================================

Covers:
  * Why transactions require a replica set
  * client.start_session() + session.with_transaction()
  * Read and write concerns in transactions
  * Retryable writes and transient error handling
  * The "bank transfer" canonical example

WHY TRANSACTIONS NEED A REPLICA SET
-------------------------------------
MongoDB's multi-document transactions are built on top of the replication
infrastructure:

  1. The transaction coordinator uses the OPLOG (the primary's write log)
     to track which writes are part of which logical transaction.
  2. The distributed snapshot mechanism (used for "snapshot" read concern)
     requires replication metadata (clusterTime, opTime) to be present.
  3. Even a single-node mongod must be started with --replSet and initiated
     (rs.initiate()) before transactions are available.

If you try to run a transaction against a standalone mongod (no --replSet),
PyMongo raises:
  pymongo.errors.OperationFailure: Transaction numbers are only allowed on
  a replica set member or mongos

RUNNING
-------
  # Requires the Docker Compose replica set:
  cd mongodb/ && docker compose up -d
  python3 mongodb/examples/04_transactions.py

  # With custom URI:
  MONGODB_URI="mongodb://host:27017/?replicaSet=rs0" python3 04_transactions.py

GRACEFUL DEGRADATION
--------------------
  If no server is reachable OR the server does not support transactions
  (standalone), the script prints clear instructions and exits cleanly.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

from pymongo import MongoClient
from pymongo.errors import (
    ConnectionFailure,
    ServerSelectionTimeoutError,
    OperationFailure,
    PyMongoError,
)

CONNECTION = os.getenv("MONGODB_URI", "mongodb://localhost:27017/?replicaSet=rs0")
TIMEOUT_MS = 4000


# =============================================================================
# Connection helper
# =============================================================================
def get_client() -> MongoClient:
    """
    Connect and verify the server is reachable.
    Raises ConnectionFailure / ServerSelectionTimeoutError on failure.
    """
    client = MongoClient(CONNECTION, serverSelectionTimeoutMS=TIMEOUT_MS)
    client.admin.command("ping")
    return client


# =============================================================================
# DEMO: credit transfer between accounts
# =============================================================================
def seed_accounts(db) -> None:
    """Set up two accounts with known starting balances."""
    db.accounts.drop()
    db.accounts.insert_many([
        {"_id": "alice", "balance": 500.00, "currency": "USD"},
        {"_id": "bob",   "balance": 200.00, "currency": "USD"},
    ])
    print("Seeded accounts:")
    for acc in db.accounts.find():
        print(f"  {acc['_id']}: ${acc['balance']:.2f}")


def transfer_credits(client: MongoClient, db_name: str,
                     from_id: str, to_id: str, amount: float) -> None:
    """
    Transfer `amount` credits from `from_id` to `to_id` atomically.

    Key PyMongo transaction patterns:
    ─────────────────────────────────
    1. client.start_session()
         Creates a *client session* — a logical grouping of operations that
         share a consistent view of the data and causal consistency.

    2. session.with_transaction(callback, ...)
         * Calls `callback(session)`.
         * If the callback raises a *transient* error (e.g. write conflict),
           with_transaction automatically RETRIES the callback.
         * If the callback raises a non-transient error, it propagates up.
         * Handles commit retries too (a successful commit might still get a
           retryable network error — with_transaction re-tries the commitTransaction).

    3. All operations inside the callback MUST pass `session=s`.
         Without `session=`, the operation runs OUTSIDE the transaction.

    4. Read concern "snapshot" gives the transaction a consistent point-in-time
       view.  Write concern "majority" ensures durability on failover.
    """
    print(f"\nTransferring ${amount:.2f} from {from_id} → {to_id}...")

    with client.start_session() as session:
        def _do_transfer(s):
            """
            Transaction body.  Called by with_transaction — may be retried
            on transient errors (write conflicts, transient network issues).
            """
            accounts = s.client[db_name].accounts

            # Debit the sender.  $inc with a negative value decrements.
            result = accounts.update_one(
                {"_id": from_id},
                {"$inc": {"balance": -amount}},
                session=s,      # ← MUST pass the session
            )
            if result.matched_count == 0:
                # Raising a non-transient exception aborts the transaction
                # and does NOT retry.
                raise ValueError(f"Account '{from_id}' not found")

            # Check sufficient funds (inside the transaction, so we see
            # the deducted balance — prevents double-spend).
            sender = accounts.find_one({"_id": from_id}, session=s)
            if sender["balance"] < 0:
                raise ValueError(
                    f"Insufficient funds: {from_id} would go negative "
                    f"(attempted ${amount:.2f}, "
                    f"available ${sender['balance'] + amount:.2f})"
                )

            # Credit the receiver.
            accounts.update_one(
                {"_id": to_id},
                {"$inc": {"balance": amount}},
                session=s,
            )

            # Log the transfer as an audit record (also inside the transaction).
            s.client[db_name].transfers.insert_one({
                "from":      from_id,
                "to":        to_id,
                "amount":    amount,
                "timestamp": datetime.now(timezone.utc),
            }, session=s)

        # with_transaction wraps the callback in startTransaction /
        # commitTransaction, and handles transient error retries.
        session.with_transaction(
            _do_transfer,
            read_concern=None,                           # use collection defaults
            write_concern=None,                          # use collection defaults
        )

    print("Transfer committed successfully.")


def show_balances(db) -> None:
    print("Account balances:")
    for acc in db.accounts.find().sort("_id"):
        print(f"  {acc['_id']}: ${acc['balance']:.2f}")

    print("Transfer log:")
    for t in db.transfers.find().sort("timestamp"):
        print(f"  {t['from']} → {t['to']}: ${t['amount']:.2f} at {t['timestamp'].strftime('%H:%M:%S')}")


def demo_failed_transfer(client: MongoClient, db_name: str) -> None:
    """
    Demonstrate that a failed transfer leaves balances unchanged.
    We attempt to transfer $1000 from alice who only has $250 left.
    """
    print("\n── Demonstrating failed transaction ──")

    with client.start_session() as session:
        def _overspend(s):
            accounts = s.client[db_name].accounts

            accounts.update_one({"_id": "alice"}, {"$inc": {"balance": -1000}}, session=s)

            # Check balance and raise ValueError — this is NOT a transient error,
            # so with_transaction will NOT retry; it aborts the transaction.
            alice = accounts.find_one({"_id": "alice"}, session=s)
            if alice["balance"] < 0:
                raise ValueError(f"alice would go negative: ${alice['balance']:.2f}")

            accounts.update_one({"_id": "bob"}, {"$inc": {"balance": 1000}}, session=s)

        try:
            session.with_transaction(_overspend)
            print("  ERROR: Transaction should have been rejected!")
        except ValueError as e:
            print(f"  Transaction aborted as expected: {e}")

    print("Balances after aborted transfer (should be unchanged):")
    for acc in client[db_name].accounts.find().sort("_id"):
        print(f"  {acc['_id']}: ${acc['balance']:.2f}")


# =============================================================================
# MAIN
# =============================================================================
def main() -> None:
    print("=" * 60)
    print(" 04_transactions.py — Multi-Document ACID Transactions")
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
        print("  Transactions require a running replica set.")
        print("  Start one with Docker Compose:")
        print()
        print("    cd mongodb/")
        print("    docker compose up -d")
        print("    # wait ~10 seconds, then re-run:")
        print("    python3 mongodb/examples/04_transactions.py")
        sys.exit(0)

    DB_NAME = "guestbook_txn_demo"
    db = client[DB_NAME]

    try:
        # Setup.
        db.transfers.drop()
        seed_accounts(db)

        # Successful transfer: alice → bob, $100.
        transfer_credits(client, DB_NAME, "alice", "bob", 100.00)
        show_balances(db)

        # Another transfer: bob → alice, $50.
        transfer_credits(client, DB_NAME, "bob", "alice", 50.00)
        show_balances(db)

        # Demonstrate a failed / aborted transaction.
        demo_failed_transfer(client, DB_NAME)

    except OperationFailure as exc:
        # OperationFailure with code 263 = "Transaction numbers are only allowed
        # on a replica set member or mongos" — i.e. standalone mongod.
        if exc.code in (263, 20):
            print("\n[ERROR] Transactions are not supported on this server.")
            print("  This usually means MongoDB was started WITHOUT --replSet.")
            print()
            print("  The Docker Compose setup in mongodb/docker-compose.yml")
            print("  starts mongod with --replSet rs0.  Make sure you are")
            print("  connecting to that instance, not a standalone mongod.")
            print()
            print("  URI used:", CONNECTION)
        else:
            print(f"\n[ERROR] MongoDB operation error: {exc}")
        sys.exit(0)
    except PyMongoError as exc:
        print(f"\n[ERROR] Unexpected MongoDB error: {exc}")
        sys.exit(1)
    finally:
        client.close()

    print("\n✓ 04_transactions.py complete.")


if __name__ == "__main__":
    main()
