"""
run_all.py — Run all MongoDB example scripts in sequence
=========================================================

Executes 01_crud, 02_aggregation, and 03_indexes (all gracefully degrade
to mongomock when no server is available).

Skips 04_transactions and 05_change_streams if no real replica set is
detected, since those features require a running replica set.

RUNNING
-------
  python3 mongodb/examples/run_all.py

  With a real server:
    cd mongodb/ && docker compose up -d
    MONGODB_URI="mongodb://localhost:27017/?replicaSet=rs0" python3 run_all.py
"""
from __future__ import annotations

import importlib
import sys
import time
import traceback

from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

CONNECTION = __import__("os").environ.get(
    "MONGODB_URI", "mongodb://localhost:27017/?replicaSet=rs0"
)
TIMEOUT_MS = 3000

# ANSI colours for a readable summary (disabled on non-TTY).
_IS_TTY = sys.stdout.isatty()
GREEN  = "\033[32m" if _IS_TTY else ""
YELLOW = "\033[33m" if _IS_TTY else ""
RED    = "\033[31m" if _IS_TTY else ""
RESET  = "\033[0m"  if _IS_TTY else ""
BOLD   = "\033[1m"  if _IS_TTY else ""


def check_server() -> bool:
    """Return True if *any* MongoDB server answers a ping at CONNECTION."""
    try:
        client = MongoClient(CONNECTION, serverSelectionTimeoutMS=TIMEOUT_MS)
        client.admin.command("ping")
        client.close()
        return True
    except Exception:
        return False


def check_replica_set() -> bool:
    """
    Return True if a replica-set-enabled MongoDB is reachable at CONNECTION.
    Checks for both connectivity AND replica-set mode.
    """
    try:
        client = MongoClient(CONNECTION, serverSelectionTimeoutMS=TIMEOUT_MS)
        client.admin.command("ping")
        # rs.status() throws if not a replica set.
        status = client.admin.command("replSetGetStatus")
        # We need at least one PRIMARY to run transactions / change streams.
        has_primary = any(
            m.get("stateStr") == "PRIMARY" for m in status.get("members", [])
        )
        client.close()
        return has_primary
    except Exception:
        return False


def run_module(module_name: str) -> tuple[bool, float]:
    """
    Import and call main() of a sibling module.
    Returns (success: bool, elapsed_seconds: float).
    """
    # Allow importing siblings whether run from the examples/ dir or the repo root.
    import importlib.util, os, pathlib
    examples_dir = pathlib.Path(__file__).parent
    spec = importlib.util.spec_from_file_location(
        module_name, examples_dir / f"{module_name}.py"
    )
    mod  = importlib.util.module_from_spec(spec)
    t0   = time.time()
    try:
        spec.loader.exec_module(mod)
        mod.main()
        return True, time.time() - t0
    except SystemExit as e:
        # The example scripts call sys.exit(0) on graceful degradation.
        # Treat that as a warning, not a failure.
        return (e.code == 0), time.time() - t0
    except Exception:
        traceback.print_exc()
        return False, time.time() - t0


def separator(title: str) -> None:
    width = 60
    print()
    print("=" * width)
    print(f"  {title}")
    print("=" * width)


def main() -> None:
    print(f"{BOLD}{'=' * 60}")
    print(" MongoDB Examples — run_all.py")
    print(f"{'=' * 60}{RESET}")
    print(f" URI: {CONNECTION}")
    print()

    server_up = check_server()
    has_replica_set = check_replica_set()
    if has_replica_set:
        print(f"{GREEN}✓ Replica set detected — all examples will run.{RESET}")
    elif server_up:
        print(f"{YELLOW}⚠ Server reachable but not a replica set.")
        print(f"  01_crud / 02_aggregation / 03_indexes → will run.")
        print(f"  04_transactions / 05_change_streams  → SKIPPED (need replica set).{RESET}")
    else:
        print(f"{YELLOW}⚠ No MongoDB server reachable — all examples will be SKIPPED.")
        print(f"  Start one, then re-run:")
        print(f"    cd mongodb/ && docker compose up -d{RESET}")

    # ── Scripts that need any reachable server ───────────────────────────────
    server_scripts = [
        ("01_crud",        "CRUD operations"),
        ("02_aggregation", "Aggregation pipeline"),
        ("03_indexes",     "Index types + explain()"),
    ]

    # ── Scripts that require a real replica set ──────────────────────────────
    replica_scripts = [
        ("04_transactions", "Multi-document ACID transactions"),
        ("05_change_streams", "Real-time change streams"),
    ]

    results: list[tuple[str, str, bool, float, str]] = []
    # (module, label, success, elapsed, note)

    for module, label in server_scripts:
        if not server_up:
            separator(f"{label}  ({module}.py) — SKIPPED")
            print(f"{YELLOW}  Skipped: no MongoDB server reachable.{RESET}")
            results.append((module, label, None, 0.0, "SKIPPED (no server)"))
            continue
        separator(f"{label}  ({module}.py)")
        ok, elapsed = run_module(module)
        note = "" if ok else "FAILED"
        results.append((module, label, ok, elapsed, note))

    for module, label in replica_scripts:
        if not has_replica_set:
            separator(f"{label}  ({module}.py) — SKIPPED")
            print(f"{YELLOW}  Skipped: replica set not available.{RESET}")
            results.append((module, label, None, 0.0, "SKIPPED (no replica set)"))
        else:
            separator(f"{label}  ({module}.py)")
            ok, elapsed = run_module(module)
            note = "" if ok else "FAILED"
            results.append((module, label, ok, elapsed, note))

    # ── Summary ──────────────────────────────────────────────────────────────
    print()
    print(f"{BOLD}{'=' * 60}")
    print(" SUMMARY")
    print(f"{'=' * 60}{RESET}")
    print(f"  {'Module':<24} {'Status':<10} {'Time':>6}  Notes")
    print(f"  {'-'*24} {'-'*10} {'-'*6}  {'-'*25}")

    all_passed = True
    for module, _label, ok, elapsed, note in results:
        if ok is True:
            status = f"{GREEN}PASS{RESET}"
        elif ok is False:
            status = f"{RED}FAIL{RESET}"
            all_passed = False
        else:
            status = f"{YELLOW}SKIP{RESET}"
        time_str = f"{elapsed:.1f}s" if elapsed else "  —"
        print(f"  {module:<24} {status:<18} {time_str:>6}  {note}")

    print()
    if all_passed:
        print(f"{GREEN}{BOLD}All runnable scripts completed successfully.{RESET}")
    else:
        print(f"{RED}Some scripts failed — see output above.{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
