"""The scripted policy behind MockProvider.

A rule-based stand-in for the model so the harness runs offline. Each agent
role follows a written script of tool calls — the same calls a real model
makes on this task — and the policy reacts to actual tool results (it reads
the test output it gets back; it does not pretend).

Two things worth noticing:

  - State lives HERE, keyed by agent id, not in the context window. That is
    cheating (a real model has no memory outside its context), and it is
    exactly why this policy survives compaction unharmed while a real model
    depends on the quality of the compaction summary. The cheat is what
    makes the demo deterministic.

  - The orchestrator's step 7 issues TWO tool_use blocks in one turn —
    parallel tool calls — so the loop's 'all results in one user message'
    rule is exercised.
"""

from __future__ import annotations

import itertools
import re
from typing import Any

from .providers import ModelRequest

FIXED_STATS_PY = '''"""Tiny numeric core for the demo project.

All functions reject empty/degenerate input with ValueError, per the team
style guide ("never return None to signal failure").
"""

import math


def mean(values):
    """Return the arithmetic mean of a non-empty sequence."""
    values = list(values)
    if not values:
        raise ValueError("mean() requires at least one value")
    return sum(values) / len(values)


def median(values):
    """Return the median of a non-empty sequence."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("median() requires at least one value")
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def stdev(values):
    """Return the SAMPLE standard deviation (n-1 denominator)."""
    values = list(values)
    if len(values) < 2:
        raise ValueError("stdev() requires at least two values")
    m = mean(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / (len(values) - 1))
'''

PLAN_INITIAL = (
    '[{"task": "Check the sprint tickets for scope", "status": "in_progress"},'
    ' {"task": "Research requirements (docs + current code)", "status": "pending"},'
    ' {"task": "Implement stdev() and fix median() empty-input crash", "status": "pending"},'
    ' {"task": "Independent review + test run", "status": "pending"},'
    ' {"task": "Open PR, update tickets, record lessons", "status": "pending"}]'
)
PLAN_DONE = PLAN_INITIAL.replace('"in_progress"', '"completed"').replace('"pending"', '"completed"')


class MockPolicy:
    def __init__(self) -> None:
        self._step: dict[str, int] = {}       # agent id -> next script index
        self._ids = itertools.count(1)

    # ------------------------------------------------------------------ decide

    def decide(self, request: ModelRequest) -> tuple[list[dict[str, Any]], str]:
        agent_id = self._agent_id(request)
        script = getattr(self, f"_script_{request.agent_role}", self._script_generic)(request)
        index = self._step.get(agent_id, 0)
        self._step[agent_id] = index + 1

        if index >= len(script):
            return [_text("Task complete.")], "end_turn"

        step = script[index]
        if step["kind"] == "final":
            return [_text(step["text"](request) if callable(step["text"]) else step["text"])], "end_turn"

        blocks: list[dict[str, Any]] = []
        if step.get("say"):
            blocks.append(_text(step["say"]))
        for name, args in step["calls"]:
            blocks.append({
                "type": "tool_use",
                "id": f"toolu_mock_{next(self._ids)}",
                "name": name,
                "input": args,
            })
        return blocks, "tool_use"

    # ----------------------------------------------------------------- scripts

    def _script_orchestrator(self, request: ModelRequest) -> list[dict]:
        return [
            _call("Planning the work first.", [("write_plan", {"todos_json": PLAN_INITIAL})]),
            _call("Checking the sprint board over MCP.",
                  [("mcp__tickets__list_tickets", {"status": "todo"})]),
            _call("Delegating research to a sub-agent so raw file contents stay out of my context.",
                  [("spawn_subagent", {
                      "role": "researcher",
                      "task": "Research what is required to (a) add stdev() to stats.py and "
                              "(b) fix median() crashing on empty input. Consult the docs MCP "
                              "server for the stats-module design notes and the style guide, "
                              "read stats.py and test_stats.py, and report the exact requirements."})]),
            _call("Research done — delegating implementation.",
                  [("spawn_subagent", {
                      "role": "coder",
                      "task": "In stats.py: add stdev() (SAMPLE standard deviation, n-1 denominator, "
                              "ValueError on fewer than 2 values) and make mean()/median() raise "
                              "ValueError on empty input instead of crashing. The tests in "
                              "test_stats.py already encode these requirements — run them first to "
                              "see the failures, fix the code, then prove the suite passes."})]),
            _call("Implementation reported green — getting an independent review.",
                  [("spawn_subagent", {
                      "role": "reviewer",
                      "task": "Review the just-changed stats.py: re-run the full test suite and "
                              "verify empty-input handling raises ValueError everywhere. "
                              "Report approve or reject with reasons."})]),
            _call("All steps done — updating the plan.", [("write_plan", {"todos_json": PLAN_DONE})]),
            # Parallel tool use: one turn, three calls, results come back together.
            _call("Closing the loop: PR plus ticket updates in parallel.",
                  [("github_create_pr", {
                      "title": "stats: add stdev(), reject empty input with ValueError",
                      "body": "Adds sample stdev (n-1) and fixes mean()/median() to raise "
                              "ValueError on empty input. Full pytest suite green. "
                              "Researched, implemented and reviewed by separate sub-agents.",
                      "branch": "feature/stats-stdev"}),
                   ("mcp__tickets__update_ticket", {"key": "DEMO-41", "status": "done"}),
                   ("mcp__tickets__update_ticket", {"key": "DEMO-42", "status": "done"})]),
            _call("Recording a durable lesson in project memory.",
                  [("memory_learn", {
                      "lesson": "stats.stdev() is SAMPLE stdev (n-1) by design review decision; "
                                "all stats functions raise ValueError on empty input."})]),
            _final(
                "Done. Added stdev() (sample, n-1) and fixed the empty-input crashes in "
                "mean()/median(); the full pytest suite passes. Work was split across a "
                "researcher, a coder and an independent reviewer, each in an isolated "
                "context. PR opened (feature/stats-stdev), tickets DEMO-41/DEMO-42 closed, "
                "and the n-1 design decision is now recorded in AGENT.md."),
        ]

    def _script_researcher(self, request: ModelRequest) -> list[dict]:
        return [
            _call("Searching the knowledge base first.",
                  [("mcp__docs__search_docs", {"query": "stdev stats requirements"})]),
            _call(None, [("mcp__docs__read_doc", {"doc_id": "stats-module"})]),
            _call("Checking the style guide for error conventions.",
                  [("mcp__docs__read_doc", {"doc_id": "style-guide"})]),
            _call("Now the current code.", [("read_file", {"path": "stats.py"})]),
            _call(None, [("read_file", {"path": "test_stats.py"})]),
            _call("Saving findings before they get compacted away.",
                  [("memory_note", {
                      "topic": "research",
                      "content": "stdev must be SAMPLE stdev (n-1), ValueError if <2 values. "
                                 "mean()/median() currently crash on empty input; style guide "
                                 "mandates ValueError with actionable message. Tests already "
                                 "encode all of this and currently fail (stdev missing)."})]),
            _final(
                "Briefing: (1) stdev() must implement SAMPLE standard deviation with the n-1 "
                "denominator per the 2024 design review (docs: stats-module), raising ValueError "
                "for fewer than 2 values. (2) mean() and median() crash on empty input today; "
                "the style guide requires raising ValueError with an actionable message instead. "
                "(3) test_stats.py already encodes both requirements — the suite currently fails "
                "because stdev is missing, so it doubles as the acceptance criteria."),
        ]

    def _script_coder(self, request: ModelRequest) -> list[dict]:
        return [
            _call("Running the tests first to see the real failures.",
                  [("run_command", {"command": "python3 -m pytest -q"})]),
            _call("As expected. Reading the module before changing it.",
                  [("read_file", {"path": "stats.py"})]),
            _call("Rewriting stats.py with stdev() and empty-input guards.",
                  [("write_file", {"path": "stats.py", "content": FIXED_STATS_PY})]),
            _call("Proving the fix.", [("run_command", {"command": "python3 -m pytest -q"})]),
            _call(None,
                  [("memory_note", {"topic": "implementation",
                                    "content": "stats.py rewritten: stdev (sample, n-1) added; "
                                               "mean/median raise ValueError on empty. pytest green."})]),
            _final(self._coder_report),
        ]

    def _coder_report(self, request: ModelRequest) -> str:
        last = _last_tool_result_text(request, contains="exit code")
        verdict = "the full suite passes" if _tests_passed(last) else \
                  f"WARNING — tests still failing:\n{last[:300]}"
        return ("Implemented: stats.py now has stdev() (sample standard deviation, n-1, "
                "ValueError below 2 values) and mean()/median() raise ValueError on empty "
                f"input. Verified by re-running pytest: {verdict}.")

    def _script_reviewer(self, request: ModelRequest) -> list[dict]:
        return [
            _call("Reading the changed module.", [("read_file", {"path": "stats.py"})]),
            _call("Re-running the suite myself.",
                  [("run_command", {"command": "python3 -m pytest -q"})]),
            _call("Spot-checking the error-handling convention.",
                  [("grep", {"pattern": "raise ValueError", "glob": "*.py"})]),
            _final(self._review_report),
        ]

    def _review_report(self, request: ModelRequest) -> str:
        last = _last_tool_result_text(request, contains="exit code")
        if _tests_passed(last):
            return ("APPROVE. stdev() matches the n-1 design decision, all three functions "
                    "raise ValueError on bad input per the style guide, and the pytest suite "
                    "passes on my independent run.")
        return f"REJECT. Test suite is not green on my run:\n{last[:400]}"

    def _script_generic(self, request: ModelRequest) -> list[dict]:
        return [
            _call("Surveying the workspace.", [("glob", {"pattern": "**/*.py"})]),
            _call(None, [("read_file", {"path": "stats.py"})]),
            _final("Plan: 1) add stdev() with n-1 denominator and a <2-values guard; "
                   "2) add empty-input ValueError guards to mean() and median(); "
                   "3) run pytest to confirm; 4) open a PR referencing DEMO-41/DEMO-42."),
        ]

    # ---------------------------------------------------------------- summarize

    def summarize(self, text: str, instruction: str) -> str:
        """Deterministic 'summarization': keep the load-bearing lines."""
        keywords = ("decid", "valueerror", "stdev", "median", "mean", "pass", "fail",
                    "error", ".py", "->", "require", "approve", "reject")
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        kept = [l for l in lines if any(k in l.lower() for k in keywords)][:12]
        summary = "\n".join(f"- {l[:160]}" for l in kept) or text[:400]
        return f"(mock summary)\n{summary}"

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _agent_id(request: ModelRequest) -> str:
        match = re.search(r"you are agent (\S+?)(?:,|\s|$)", request.system)
        return match.group(1) if match else request.agent_role


def _text(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def _call(say: str | None, calls: list[tuple[str, dict]]) -> dict:
    return {"kind": "calls", "say": say, "calls": calls}


def _final(text) -> dict:
    return {"kind": "final", "text": text}


def _last_tool_result_text(request: ModelRequest, contains: str = "") -> str:
    """Read actual tool results out of the conversation (newest first)."""
    for message in reversed(request.messages):
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in reversed(content):
            if isinstance(block, dict) and block.get("type") == "tool_result":
                text = block.get("content", "")
                if isinstance(text, list):
                    text = " ".join(str(c.get("text", "")) for c in text if isinstance(c, dict))
                if not contains or contains in str(text):
                    return str(text)
    return ""


def _tests_passed(pytest_output: str) -> bool:
    return "exit code 0" in pytest_output and "passed" in pytest_output
