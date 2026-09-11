#!/usr/bin/env bash
# Propagate the root AGENTS.md into every repo as AGENTS.global.md, and verify
# each repo's own AGENTS.md points at it.
#
#   ./scripts/sync-rules.sh          copy + verify
#   ./scripts/sync-rules.sh --check  verify only (exit 1 on drift)
#
# Why this exists: agents auto-load `AGENTS.md` from the repo they are opened in.
# `AGENTS.global.md` is NOT a discovery filename -- nothing reads it unless the
# repo's own AGENTS.md says to. A copy that silently goes stale, or that nothing
# ever reads, is the same failure this project's drift test exists to prevent,
# one level up.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/AGENTS.md"
REPOS=(01-contracts 02-infra 03-ingest 04-pipelines 05-serving 06-chatbot)
CHECK_ONLY=0
[ "${1:-}" = "--check" ] && CHECK_ONLY=1

fail=0
for r in "${REPOS[@]}"; do
  dir="$ROOT/1sde-edgar-$r"
  dst="$dir/AGENTS.global.md"
  own="$dir/AGENTS.md"

  if [ ! -d "$dir" ]; then
    echo "MISSING REPO  $r"; fail=1; continue
  fi

  if [ "$CHECK_ONLY" -eq 1 ]; then
    if ! diff -q "$SRC" "$dst" >/dev/null 2>&1; then
      echo "STALE         $r/AGENTS.global.md differs from root AGENTS.md"; fail=1
    fi
  else
    cp "$SRC" "$dst"
  fi

  # The pointer is what makes the copy reachable. Without it the file is inert.
  if ! grep -q "AGENTS.global.md" "$own" 2>/dev/null; then
    echo "NO POINTER    $r/AGENTS.md does not reference AGENTS.global.md"; fail=1
  fi
done

if [ "$fail" -eq 0 ]; then
  echo "rules in sync across ${#REPOS[@]} repos"
fi
exit "$fail"
