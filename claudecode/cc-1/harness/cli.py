"""Terminal front-end.

    python3 -m harness.cli "your task here"            # mock provider
    python3 -m harness.cli --provider anthropic "..."  # real Claude
    python3 -m harness.cli --resume <session-id> "..." # carry notes forward
    python3 -m harness.cli --list                      # show past sessions

Rendering is just an event-bus subscriber — the same events the Angular UI
consumes over SSE.
"""

from __future__ import annotations

import argparse
import sys

from .events import Event
from .runner import SESSIONS_ROOT, run_task
from .session import SessionStore

DIM, BOLD, RESET = "\x1b[2m", "\x1b[1m", "\x1b[0m"
COLORS = {"agent.spawned": "\x1b[35m", "agent.completed": "\x1b[32m", "tool.call": "\x1b[36m",
          "mcp.call": "\x1b[34m", "compaction": "\x1b[33m", "plan.updated": "\x1b[95m"}


def render(event: Event) -> None:
    color = COLORS.get(event.type, DIM)
    agent = f"{event.agent_id or 'harness'}"
    data = event.data
    if event.type == "agent.spawned":
        line = f"spawn {data['role']}  parent={data['parent'] or '—'}  task={data['task'][:80]}…"
    elif event.type == "agent.completed":
        ctx = data.get("context", {})
        line = (f"done after {data['turns']} turns  "
                f"ctx {ctx.get('used_tokens')}/{ctx.get('max_tokens')}t "
                f"({ctx.get('compactions', 0)} compactions)")
    elif event.type == "agent.turn":
        calls = ",".join(data.get("tool_calls", [])) or "final answer"
        util = data.get("context", {}).get("utilization", 0)
        line = f"turn {data['turn']}  ctx {util:.0%}  -> {calls}"
    elif event.type == "tool.call":
        ok = "ok" if data["ok"] else "ERR"
        line = f"{data['tool']} [{ok} {data['duration_ms']}ms] {str(data.get('output_preview',''))[:90]}"
    elif event.type == "mcp.call":
        line = f"MCP {data['server']}.{data['tool']} -> {data.get('result_preview','')[:80]}"
    elif event.type == "compaction":
        line = (f"COMPACTED {data['turns_compacted']} turns: "
                f"{data['tokens_before']}t -> {data['tokens_after']}t")
    elif event.type == "plan.updated":
        done = sum(1 for t in data["todos"] if t["status"] == "completed")
        line = f"plan: {done}/{len(data['todos'])} done"
    elif event.type.startswith("session."):
        line = str({k: v for k, v in data.items() if k != "task"})[:120]
    elif event.type == "mcp.connected":
        line = f"connected MCP server '{data['server']}' tools={data['tools']}"
    else:
        line = str(data)[:120]
    print(f"{color}{event.type:<16}{RESET} {BOLD}{agent:<16}{RESET} {line}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cc-1")
    parser.add_argument("task", nargs="?", help="what to do")
    parser.add_argument("--provider", default="mock", choices=["mock", "anthropic", "bedrock"])
    parser.add_argument("--resume", metavar="SESSION_ID", help="carry a past session's notes forward")
    parser.add_argument("--list", action="store_true", help="list past sessions")
    args = parser.parse_args(argv)

    store = SessionStore(SESSIONS_ROOT)
    if args.list:
        for state in store.list():
            print(f"{state['id']}  {state['status']:<10} {str(state.get('task'))[:70]}")
        return 0

    if not args.task:
        parser.error("a task is required (or --list)")

    print(f"{BOLD}cc-1{RESET} provider={args.provider}\n")
    finished = run_task(args.task, provider_name=args.provider, store=store,
                        resume_from=args.resume, on_event=render)
    print(f"\n{BOLD}session {finished.id}: {finished.state['status']}{RESET}")
    print(finished.state["result"])
    return 0 if finished.state["status"] == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
