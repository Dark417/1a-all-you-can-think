"""Offline eval harness.

For each row in `golden.jsonl`:
  - run one full ReAct turn against a fresh controller,
  - check `must_include` substrings are present in the answer,
  - check the expected tool was invoked at least once (looking at the
    session trace),
  - print a per-case pass/fail and a final summary.

This is the simplest possible eval — no LLM-as-judge, no scoring model.
It's enough to catch regressions when you change prompts, swap models,
or refactor the controller."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from ..controller import Controller
from ..llm import LLM, LLMError
from ..memory import ConversationMemory, NoteStore
from ..tools import default_registry
from ..tracing import Tracer
from ..vectorstore import VectorStore

console = Console()
GOLDEN = Path(__file__).parent / "golden.jsonl"


def _load_cases() -> list[dict]:
    with GOLDEN.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def _check_trace_for_tool(trace_path: Path, tool_name: str) -> bool:
    if not trace_path.exists():
        return False
    for line in trace_path.read_text().splitlines():
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("event") == "tool_call" and rec.get("data", {}).get("name") == tool_name:
            return True
    return False


def main() -> int:
    try:
        llm = LLM()
    except LLMError as e:
        console.print(f"[red]{e}[/red]")
        return 1

    cases = _load_cases()
    table = Table(title=f"Atlas eval — {len(cases)} cases", border_style="dim")
    table.add_column("id")
    table.add_column("text-pass")
    table.add_column("tool-pass")
    table.add_column("iters")
    table.add_column("tools")

    passed = 0
    for case in cases:
        store = VectorStore()
        notes = NoteStore()
        registry = default_registry(vector_store=store, note_store=notes)
        tracer = Tracer()
        controller = Controller(
            llm=llm, tools=registry,
            memory=ConversationMemory(), tracer=tracer,
        )

        result = controller.run_turn(case["question"])
        answer = (result.text or "").lower()
        text_ok = all(s.lower() in answer for s in case.get("must_include", []))
        tool_ok = _check_trace_for_tool(tracer.path, case["tool_expected"]) \
            if case.get("tool_expected") else True

        case_pass = text_ok and tool_ok
        passed += int(case_pass)
        table.add_row(
            case["id"],
            "[green]✓[/green]" if text_ok else "[red]✗[/red]",
            "[green]✓[/green]" if tool_ok else "[red]✗[/red]",
            str(result.iterations),
            str(result.tool_calls),
        )

    console.print(table)
    console.print(f"[bold]{passed}/{len(cases)} passed.[/bold]")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
