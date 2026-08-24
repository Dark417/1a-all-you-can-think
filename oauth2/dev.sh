#!/usr/bin/env bash
# Starts the backend and all three UIs. Ctrl-C stops everything.
set -euo pipefail
cd "$(dirname "$0")"

for dir in backend react angular nextjs; do
  if [ ! -d "$dir/node_modules" ]; then
    echo "installing $dir ..."
    (cd "$dir" && npm install --no-audit --no-fund)
  fi
done

[ -f backend/.env ] || cp backend/.env.example backend/.env

pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

(cd backend && npm run dev)  & pids+=($!)
sleep 2
(cd react   && npm run dev)  & pids+=($!)
(cd angular && npm run dev)  & pids+=($!)
(cd nextjs  && npm run dev)  & pids+=($!)

cat <<'BANNER'

  backend   http://localhost:8080
  react     http://localhost:5173
  angular   http://localhost:4200
  nextjs    http://localhost:3000

  sign in as alice (admin) or bob (viewer), password Password1!

BANNER

wait
