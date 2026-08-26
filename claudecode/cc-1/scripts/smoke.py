"""End-to-end proof that every mechanism in the harness actually happens.

    python3 scripts/smoke.py

Runs the demo task offline (mock provider) in a throwaway sessions dir, then
asserts against the event stream, the workspace, and the memory files —
plan, tools, BOTH MCP servers, sub-agent spawning + isolation, parallel tool
use, compaction, memory, session persistence, and resume.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.runner import PLAYGROUND, run_task  # noqa: E402
from harness.session import SessionStore  # noqa: E402

passed = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global passed
    if condition:
        passed += 1
        print(f"  \x1b[32m✓\x1b[0m {label}")
    else:
        print(f"  \x1b[31m✗\x1b[0m {label}{('  -> ' + detail) if detail else ''}")
        raise SystemExit(f"FAILED: {label}")


def main() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="cc1-smoke-"))
    store = SessionStore(tmp)
    try:
        session = run_task(
            "Work the open tickets: add stdev() and fix the median() crash.",
            provider_name="mock", store=store,
        )
        events = [e.to_dict() for e in session.bus.all()]
        by_type: dict[str, list[dict]] = {}
        for e in events:
            by_type.setdefault(e["type"], []).append(e)
        state = json.loads((session.dir / "state.json").read_text())

        print("\n1. the agent loop ran and finished")
        check("session completed", state["status"] == "completed")
        check("orchestrator produced a final answer", "stdev" in str(state["result"]))
        check("events were emitted", len(events) > 40, str(len(events)))

        print("\n2. planning")
        plans = by_type.get("plan.updated", [])
        check("a plan was written", len(plans) >= 2)
        check("the plan ended fully completed",
              all(t["status"] == "completed" for t in plans[-1]["data"]["todos"]))

        print("\n3. tools (built-in)")
        tools_used = {e["data"]["tool"] for e in by_type.get("tool.call", [])}
        for name in ("write_plan", "read_file", "write_file", "run_command",
                     "github_create_pr", "memory_note", "memory_learn", "spawn_subagent", "grep"):
            check(f"{name} was called", name in tools_used)
        check("every tool call succeeded",
              all(e["data"]["ok"] for e in by_type["tool.call"]),
              str([e["data"] for e in by_type["tool.call"] if not e["data"]["ok"]]))

        print("\n4. MCP — two servers, both used")
        connected = {e["data"]["server"] for e in by_type.get("mcp.connected", [])}
        check("both MCP servers connected", connected == {"docs", "tickets"}, str(connected))
        mcp_servers_called = {e["data"]["server"] for e in by_type.get("mcp.call", [])}
        check("both MCP servers were actually called", mcp_servers_called == {"docs", "tickets"},
              str(mcp_servers_called))
        check("MCP tools are namespaced mcp__<server>__<tool>",
              any(t.startswith("mcp__docs__") for t in tools_used)
              and any(t.startswith("mcp__tickets__") for t in tools_used))

        print("\n5. sub-agents: spawning, relationships, isolation")
        spawned = by_type.get("agent.spawned", [])
        roles = [e["data"]["role"] for e in spawned]
        check("orchestrator + 3 sub-agents spawned",
              roles == ["orchestrator", "researcher", "coder", "reviewer"], str(roles))
        children = [e["data"] for e in spawned if e["data"]["parent"]]
        check("every sub-agent records its parent",
              all(c["parent"].startswith("orchestrator") for c in children))
        agents = {a["id"]: a for a in state["agents"]}
        check("agent tree persisted with per-agent context accounting",
              all("used_tokens" in a["context"] for a in agents.values()))
        researcher = next(a for a in agents.values() if a["role"] == "researcher")
        orchestrator = next(a for a in agents.values() if a["role"] == "orchestrator")
        check("contexts are isolated (researcher window is its own budget, not the parent's)",
              researcher["context"]["max_tokens"] != orchestrator["context"]["max_tokens"])
        check("parent received a summary, not the child transcript",
              len(researcher["result_summary"]) < 1200)

        print("\n6. parallel tool use")
        parallel_turns = [e for e in by_type.get("agent.turn", []) if len(e["data"]["tool_calls"]) > 1]
        check("at least one turn issued multiple tool calls", len(parallel_turns) >= 1)
        check("that turn mixed a built-in and an MCP tool",
              any({"github_create_pr", "mcp__tickets__update_ticket"} <=
                  set(t["data"]["tool_calls"]) for t in parallel_turns))

        print("\n7. compaction")
        compactions = by_type.get("compaction", [])
        check("compaction fired mid-run", len(compactions) >= 1)
        c = compactions[0]["data"]
        check("compaction freed tokens", c["tokens_after"] < c["tokens_before"],
              f"{c['tokens_before']} -> {c['tokens_after']}")
        check("compaction happened on the researcher (the tight window)",
              compactions[0]["agent_id"].startswith("researcher"))
        check("agent kept working after compaction and still finished",
              researcher["status"] == "completed")

        print("\n8. the work is real")
        stats = (session.workspace / "stats.py").read_text()
        check("stdev() exists in the workspace copy", "def stdev" in stats)
        check("empty-input guard added", "ValueError" in stats)
        check("playground original untouched",
              "def stdev" not in (PLAYGROUND / "stats.py").read_text())
        import subprocess
        proc = subprocess.run([sys.executable, "-m", "pytest", "-q"],
                              cwd=session.workspace, capture_output=True, text=True)
        check("pytest passes in the session workspace", proc.returncode == 0, proc.stdout[-200:])

        print("\n9. memory")
        notes = json.loads((session.dir / "notes.json").read_text())
        check("session notes were written by more than one agent",
              len({n["agent_id"] for n in notes}) >= 2)
        agent_md = (session.workspace / "AGENT.md").read_text()
        check("a durable lesson landed in AGENT.md", "n-1" in agent_md)

        print("\n10. session persistence + resume")
        check("events.jsonl is a full transcript",
              len(store.load_events(session.id)) == len(events))
        listed = store.list()
        check("session shows up in the store listing", any(s["id"] == session.id for s in listed))
        brief = store.resume_brief(session.id)
        check("resume brief carries notes forward, not the raw transcript",
              "Notes carried forward" in brief and "stdev" in brief and len(brief) < 3000)

        resumed = run_task("Quick follow-up: confirm the stats module state.",
                           provider_name="mock", store=store, resume_from=session.id)
        check("resumed session completed", resumed.state["status"] == "completed")
        check("resumed session saw the previous outcome",
              "Resuming session" in resumed.state["task"])

        print(f"\n\x1b[32mall {passed} checks passed\x1b[0m\n")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
